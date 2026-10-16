"""Offline capture integrity, persistence, failure and CLI contracts."""

from __future__ import annotations

import http.client
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from lib.macro_capture.bls import capture, digest, encode, fetch_http, parse, show, writer_lock

NOW = datetime(2026, 10, 16, tzinfo=UTC)
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "bls_capture.py"


def fixture(value: str = "320.100") -> bytes:
    return encode(
        {
            "status": "REQUEST_SUCCEEDED",
            "Results": {
                "series": [
                    {
                        "seriesID": "CUUR0000SA0",
                        "data": [
                            {"year": "2026", "period": "M09", "value": value},
                            {"year": "2025", "period": "M13", "value": "310.1"},
                        ],
                    }
                ]
            },
        }
    )


def make(root: Path, run: str = "one", raw: bytes | None = None, status: int = 200) -> dict:
    return capture(root, run, _fetch=lambda: (status, fixture() if raw is None else raw), _now=lambda: NOW)


def rehash(bundle: Path) -> None:
    (bundle / "manifest.json").write_bytes(
        encode({name: digest((bundle / name).read_bytes()) for name in ("response.bin", "receipt.json", "records.jsonl")})
    )


def test_success_and_idempotence(tmp_path: Path) -> None:
    first = make(tmp_path)
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in (tmp_path / "one").iterdir()}
    second = capture(tmp_path, "one", _fetch=lambda: pytest.fail("must not fetch"))
    assert first == second
    assert before == {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in (tmp_path / "one").iterdir()}
    assert first["monthly_count"] == first["excluded_annual_count"] == 1
    row = json.loads((tmp_path / "one" / "records.jsonl").read_text())
    assert row["market_public_at"] is None and row["vintage_label"] is None
    assert row["market_public_at_basis"] == "UNKNOWN"
    assert row["reference_period_start"] == "2026-09-01"


def test_revision_separate_capture(tmp_path: Path) -> None:
    make(tmp_path)
    make(tmp_path, "two", fixture("321.2"))
    a = json.loads((tmp_path / "one" / "records.jsonl").read_text())
    b = json.loads((tmp_path / "two" / "records.jsonl").read_text())
    assert a["series_id"] == b["series_id"]
    assert a["record_id"] != b["record_id"] and a["value"] != b["value"]


def test_receipt_uses_response_time_not_request_start(tmp_path: Path) -> None:
    received = NOW.replace(hour=1)
    clock = iter([NOW, received])
    result = capture(tmp_path, "timing", _fetch=lambda: (200, fixture()), _now=lambda: next(clock))
    row = json.loads((tmp_path / "timing" / "records.jsonl").read_text())
    assert result["started_at"] == NOW.isoformat()
    assert result["received_at"] == row["retrieved_at"] == received.isoformat()


@pytest.mark.parametrize("case", ["length-short", "length-invalid", "incomplete", "http-exception", "os-error", "oversize"])
def test_failed_entity_read_is_persisted_without_retry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str) -> None:
    raw = fixture()
    calls = []

    class Response:
        code = 200
        headers = {
            "Content-Length": str(len(raw) + 7)
            if case == "length-short"
            else "invalid"
            if case == "length-invalid"
            else str(len(raw))
        }

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self, count):
            assert count == 1024 * 1024 + 1
            if case == "incomplete":
                raise http.client.IncompleteRead(raw, 7)
            if case == "http-exception":
                raise http.client.HTTPException("connection interrupted")
            if case == "os-error":
                raise OSError("connection interrupted")
            return b"x" * count if case == "oversize" else raw

    class Opener:
        def open(self, request, timeout):
            calls.append(request.full_url)
            return Response()

    monkeypatch.setattr("urllib.request.build_opener", lambda *args: Opener())
    received = NOW.replace(hour=2)
    clock = iter([NOW, received])
    result = capture(tmp_path, "cut", _fetch=fetch_http, _now=lambda: next(clock))
    assert result["outcome"] == "FAILED" and result["http_status"] == 200
    assert result["received_at"] == received.isoformat()
    expected = b"" if case in {"http-exception", "os-error"} else b"x" * (1024 * 1024 + 1) if case == "oversize" else raw
    assert (tmp_path / "cut" / "response.bin").read_bytes() == expected
    assert not (tmp_path / "cut" / "records.jsonl").read_bytes()
    assert show(tmp_path, "cut") == result
    assert capture(tmp_path, "cut", _fetch=fetch_http) == result and len(calls) == 1
    cli = subprocess.run(
        [sys.executable, str(SCRIPT), "show", "--root", str(tmp_path), "--run-id", "cut"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert cli.returncode == 1 and cli.stderr
    assert json.loads(cli.stdout)["outcome"] == "FAILED"


def test_parse_failure_keeps_response_timestamp(tmp_path: Path) -> None:
    received = NOW.replace(hour=3)
    clock = iter([NOW, received])
    result = capture(tmp_path, "parse-fail", _fetch=lambda: (200, b"{}"), _now=lambda: next(clock))
    assert result["outcome"] == "FAILED" and result["received_at"] == received.isoformat()


@pytest.mark.parametrize("status", [301, 302, 401, 403, 429, 500])
def test_http_failures_saved_no_retry(tmp_path: Path, status: int) -> None:
    receipt = make(tmp_path, status=status)
    assert receipt["outcome"] == "FAILED"
    assert receipt["http_status"] == status
    assert capture(tmp_path, "one", _fetch=lambda: pytest.fail("no repeat")) == receipt


def test_network_failure_saved(tmp_path: Path) -> None:
    def fail() -> tuple[int, bytes]:
        raise TimeoutError("offline timeout")

    result = capture(tmp_path, "network", _fetch=fail, _now=lambda: NOW)
    assert result["outcome"] == "FAILED" and result["http_status"] is None
    assert show(tmp_path, "network") == result


@pytest.mark.parametrize(
    "raw",
    [b"", b"{}", b'{"status":"REQUEST_SUCCEEDED","status":"x"}', b'{"status":NaN}', b"x" * (1024 * 1024 + 1)],
    ids=["empty", "schema", "duplicate-key", "nan", "oversize"],
)
def test_invalid_response_quarantined(tmp_path: Path, raw: bytes) -> None:
    result = make(tmp_path, raw=raw)
    assert result["outcome"] == "FAILED"
    assert (tmp_path / "one" / "response.bin").read_bytes() == raw


@pytest.mark.parametrize(
    "field,value",
    [
        ("year", 2026),
        ("year", "0000"),
        ("year", "2027"),
        ("period", "M00"),
        ("period", "M14"),
        ("period", 9),
        ("value", 320),
        ("value", "NaN"),
        ("value", "Infinity"),
        ("value", "0"),
        ("value", "-1"),
    ],
)
def test_invalid_economic_fields(field: str, value: object) -> None:
    payload = json.loads(fixture())
    payload["Results"]["series"][0]["data"][0][field] = value
    with pytest.raises(ValueError):
        parse(encode(payload), NOW, "one")


def test_duplicate_month_and_zero_months() -> None:
    payload = json.loads(fixture())
    rows = payload["Results"]["series"][0]["data"]
    rows.append(rows[0])
    with pytest.raises(ValueError, match="duplicate"):
        parse(encode(payload), NOW, "one")
    payload["Results"]["series"][0]["data"] = [rows[1]]
    with pytest.raises(ValueError, match="no monthly"):
        parse(encode(payload), NOW, "one")


@pytest.mark.parametrize("name", ["response.bin", "receipt.json", "records.jsonl"])
def test_checksum_detects_change(tmp_path: Path, name: str) -> None:
    make(tmp_path)
    with (tmp_path / "one" / name).open("ab") as handle:
        handle.write(b" ")
    with pytest.raises(ValueError, match="checksum"):
        show(tmp_path, "one")


@pytest.mark.parametrize(
    "field,value",
    [
        ("value", "999"),
        ("retrieved_at", "2020-01-01T00:00:00+00:00"),
        ("market_public_at", "2026-09-01T00:00:00+00:00"),
        ("series_id", "OTHER"),
    ],
)
def test_rehash_cannot_hide_semantic_tamper(tmp_path: Path, field: str, value: str) -> None:
    make(tmp_path)
    path = tmp_path / "one" / "records.jsonl"
    row = json.loads(path.read_text())
    row[field] = value
    path.write_bytes(encode(row))
    rehash(path.parent)
    with pytest.raises(ValueError, match="mismatch"):
        show(tmp_path, "one")


def test_incomplete_staging_retained(tmp_path: Path) -> None:
    stage = tmp_path / ".staging-one"
    stage.mkdir()
    (stage / "partial").write_text("keep")
    with pytest.raises(ValueError, match="incomplete"):
        capture(tmp_path, "one", _fetch=lambda: pytest.fail("no fetch"))
    assert (stage / "partial").read_text() == "keep"
    assert not (tmp_path / "one").exists()


def test_lock_excludes_second_writer_and_releases(tmp_path: Path) -> None:
    with writer_lock(tmp_path):
        with pytest.raises(OSError), writer_lock(tmp_path):
            pytest.fail("concurrent writer")
    with writer_lock(tmp_path):
        pass


def test_show_unknown_noncreating_and_cli_any_cwd(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    with pytest.raises(FileNotFoundError):
        show(missing, "one")
    assert not missing.exists()
    make(tmp_path)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "show", "--root", str(tmp_path), "--run-id", "one"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0 and not result.stderr
    assert json.loads(result.stdout)["mode"] == "CAPTURE_ONLY"
    missing_result = subprocess.run(
        [sys.executable, str(SCRIPT), "show", "--root", str(missing), "--run-id", "one"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert missing_result.returncode != 0 and not missing.exists()


@pytest.mark.parametrize("run", ["../escape", "", "CON", "a.b", "a/b"])
def test_invalid_run_noncreating(tmp_path: Path, run: str) -> None:
    root = tmp_path / "absent"
    with pytest.raises(ValueError):
        capture(root, run)
    assert not root.exists()
