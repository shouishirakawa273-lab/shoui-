"""One fixed, unauthenticated BLS series captured in immutable local bundles."""

from __future__ import annotations

import calendar
import hashlib
import http.client
import json
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from uuid import uuid4

from lib.evaluation.store import AppendOnlyRecordStore
from lib.evidence.model import Frequency, ValueAvailability
from lib.macro.model import MacroRecord, SeasonalAdjustment

URL = "https://api.bls.gov/publicAPI/v1/timeseries/data/CUUR0000SA0"
SERIES = "CUUR0000SA0"
VERSION = "bls-capture-2"
MISSING_FOOTNOTE = {"code": "X", "text": "Data unavailable due to the 2025 lapse in appropriations"}
LIMIT = 1024 * 1024
DISCLAIMER = "Source: U.S. Bureau of Labor Statistics. BLS does not guarantee subsequent analysis."


def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def loads(raw: bytes) -> Any:
    return json.loads(raw, object_pairs_hook=unique, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def encode(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def record_dict(record: MacroRecord) -> dict[str, Any]:
    return {
        key: value.isoformat() if isinstance(value, (date, datetime)) else str(value) if isinstance(value, Decimal) else value
        for key, value in asdict(record).items()
    }


def parse(raw: bytes, received: datetime, run_id: str) -> tuple[list[MacroRecord], int]:
    """Validate economic fields; ignore unconsumed response metadata."""
    payload = loads(raw)
    if not isinstance(payload, dict) or payload.get("status") != "REQUEST_SUCCEEDED":
        raise ValueError("BLS request unsuccessful or invalid response")
    results = payload.get("Results")
    series = results.get("series") if isinstance(results, dict) else None
    if not isinstance(series, list) or len(series) != 1 or not isinstance(series[0], dict):
        raise ValueError("expected one series")
    if series[0].get("seriesID") != SERIES or not isinstance(series[0].get("data"), list):
        raise ValueError("invalid series or data")
    records: list[MacroRecord] = []
    seen: set[str] = set()
    annual = 0
    for row in series[0]["data"]:
        if not isinstance(row, dict):
            raise ValueError("invalid row")
        year, period, value = row.get("year"), row.get("period"), row.get("value")
        if (
            not isinstance(year, str)
            or not re.fullmatch(r"[0-9]{4}", year)
            or not isinstance(period, str)
            or not re.fullmatch(r"M(0[1-9]|1[0-3])", period)
        ):
            raise ValueError("invalid year/period")
        identity = f"{year}-{period}"
        if identity in seen:
            raise ValueError("duplicate period")
        seen.add(identity)
        number: Decimal | None
        availability = ValueAvailability.PRESENT
        if value == "-" and year == "2025" and period == "M10" and row.get("footnotes") == [MISSING_FOOTNOTE]:
            number = None
            availability = ValueAvailability.MISSING_OR_UNSPECIFIED
        else:
            if not isinstance(value, str) or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value):
                raise ValueError("invalid index string or unsupported missing marker/reason")
            try:
                number = Decimal(value)
            except InvalidOperation as exc:
                raise ValueError("invalid decimal") from exc
            if not number.is_finite() or number <= 0:
                raise ValueError("index must be finite and positive")
        month = int(period[1:])
        if month == 13:
            annual += 1
            continue
        start = date(int(year), month, 1)
        if start > received.date().replace(day=1):
            raise ValueError("future reference month")
        end = date(start.year, month, calendar.monthrange(start.year, month)[1])
        sid = f"BLS|{SERIES}|NSA|MONTHLY|{start:%Y-%m}"
        records.append(
            MacroRecord(
                record_id=f"{run_id}|{sid}",
                series_id=sid,
                series_code=SERIES,
                metric_name="CPI_U_ALL_ITEMS_US_CITY_AVERAGE_INDEX",
                source_id="BLS",
                frequency=Frequency.MONTHLY,
                reference_period_start=start,
                reference_period_end=end,
                raw_value=value,
                value=number,
                unit="INDEX_1982_84_100",
                seasonal_adjustment=SeasonalAdjustment.NOT_SEASONALLY_ADJUSTED,
                value_availability=availability,
                retrieved_at=received,
                raw_snapshot_ref=f"{run_id}/response.bin",
                source_field=f"Results.series[{SERIES}].data[{identity}].value",
                normalizer_version=VERSION,
            )
        )
    if not records:
        raise ValueError("no monthly observations")
    return records, annual


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


class CaptureReadError(OSError):
    """Failed entity read with observed status and any recoverable partial bytes."""

    def __init__(self, message: str, status: int | None, partial: bytes) -> None:
        super().__init__(message)
        self.status = status
        self.partial = partial


def fetch_http() -> tuple[int, bytes]:
    """One attempt, no redirect/retry; bounded entity response and socket timeout."""
    opener = urllib.request.build_opener(NoRedirect())
    request = urllib.request.Request(URL, headers={"Accept": "application/json", "User-Agent": "JapaneseEquityLab-capture/1"})
    try:
        response = opener.open(request, timeout=15)
    except urllib.error.HTTPError as exc:
        response = exc
    except http.client.HTTPException as exc:
        raise CaptureReadError(f"HTTP connection failure; partial bytes unavailable: {exc}", None, b"") from exc
    with response:
        status = int(response.code)
        try:
            raw = response.read(LIMIT + 1)
        except http.client.IncompleteRead as exc:
            raise CaptureReadError(
                "incomplete entity read; saved recoverable prefix, not complete response", status, exc.partial[: LIMIT + 1]
            ) from exc
        except (http.client.HTTPException, OSError) as exc:
            raise CaptureReadError(f"entity read failed; partial bytes unavailable: {exc}", status, b"") from exc
        length = response.headers.get("Content-Length")
        if length is not None and (not isinstance(length, str) or not re.fullmatch(r"[0-9]+", length)):
            raise CaptureReadError("invalid Content-Length; completeness unverified", status, raw)
        if len(raw) > LIMIT:
            raise CaptureReadError(
                "response exceeds 1MiB limit; saved entity prefix only, not complete response hash", status, raw
            )
        if length is not None and int(length) != len(raw):
            raise CaptureReadError("Content-Length mismatch; saved entity may be incomplete", status, raw)
        return status, raw


@contextmanager
def writer_lock(root: Path) -> Iterator[None]:
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".writer.lock").open("a+b") as handle:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            handle.seek(0)
            if sys.platform == "win32":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def check_id(run_id: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", run_id) or run_id.upper().split(".")[0] in {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }:
        raise ValueError("invalid run id")


def utc(value: str) -> datetime:
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() != UTC.utcoffset(result):
        raise ValueError("timestamp must be UTC")
    return result


def show(root: Path, run_id: str) -> dict[str, Any]:
    """Read only: verify checksums AND reconstruct records from raw economic fields."""
    check_id(run_id)
    bundle = root / run_id
    manifest = loads((bundle / "manifest.json").read_bytes())
    if not isinstance(manifest, dict) or set(manifest) != {"response.bin", "receipt.json", "records.jsonl"}:
        raise ValueError("invalid manifest")
    files = {name: (bundle / name).read_bytes() for name in manifest}
    if any(digest(raw) != manifest[name] for name, raw in files.items()):
        raise ValueError("bundle checksum mismatch")
    receipt = loads(files["receipt.json"])
    expected_fields = {
        "run_id",
        "url",
        "started_at",
        "received_at",
        "http_status",
        "outcome",
        "error",
        "raw_sha256",
        "normalizer_version",
        "monthly_count",
        "excluded_annual_count",
        "mode",
        "availability_basis",
        "citation",
        "retrieval_date",
    }
    if (
        not isinstance(receipt, dict)
        or set(receipt) != expected_fields
        or receipt["run_id"] != run_id
        or receipt["url"] != URL
        or receipt["normalizer_version"] != VERSION
        or receipt["mode"] != "CAPTURE_ONLY"
        or receipt["availability_basis"] != "SYSTEM_OBSERVED"
        or receipt["citation"] != DISCLAIMER
    ):
        raise ValueError("invalid receipt")
    started, received = utc(receipt["started_at"]), utc(receipt["received_at"])
    if (
        started > received
        or receipt["retrieval_date"] != received.date().isoformat()
        or receipt["raw_sha256"] != digest(files["response.bin"])
    ):
        raise ValueError("invalid receipt timing or raw hash")
    if (
        type(receipt["monthly_count"]) is not int
        or type(receipt["excluded_annual_count"]) is not int
        or (receipt["http_status"] is not None and type(receipt["http_status"]) is not int)
    ):
        raise ValueError("invalid counts/status")
    if receipt["outcome"] == "CAPTURED":
        records, annual = parse(files["response.bin"], received, run_id)
        rows = [loads(line) for line in files["records.jsonl"].splitlines()]
        if (
            rows != [record_dict(record) for record in records]
            or receipt["monthly_count"] != len(records)
            or receipt["excluded_annual_count"] != annual
            or receipt["http_status"] != 200
            or receipt["error"] is not None
        ):
            raise ValueError("raw/record/receipt mismatch")
    elif receipt["outcome"] == "FAILED":
        if (
            files["records.jsonl"]
            or receipt["monthly_count"] != 0
            or receipt["excluded_annual_count"] != 0
            or not isinstance(receipt["error"], str)
            or not receipt["error"]
        ):
            raise ValueError("invalid failure receipt")
    else:
        raise ValueError("invalid outcome")
    return receipt


def capture(
    root: Path,
    run_id: str | None = None,
    *,
    _fetch: Callable[[], tuple[int, bytes]] = fetch_http,
    _now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> dict[str, Any]:
    run_id = str(uuid4()) if run_id is None else run_id
    check_id(run_id)
    with writer_lock(root):
        final, stage = root / run_id, root / f".staging-{run_id}"
        if final.exists():
            return show(root, run_id)
        if stage.exists():
            raise ValueError("incomplete staging retained; use a new run id")
        stage.mkdir()
        started = _now()
        raw = b""
        status: int | None = None
        records: list[MacroRecord] = []
        annual = 0
        error: str | None = None
        received = started
        try:
            status, raw = _fetch()
            received = _now()
            if len(raw) > LIMIT:
                raise ValueError("response exceeds 1MiB limit; saved entity prefix only, not a complete response hash")
            if status != 200:
                raise ValueError(f"HTTP {status}; single attempt, no retry")
            records, annual = parse(raw, received, run_id)
        except CaptureReadError as exc:
            received = _now()
            status, raw = exc.status, exc.partial
            error = f"{type(exc).__name__}: {exc}"
            records, annual = [], 0
        except (OSError, ValueError) as exc:
            if status is None:
                received = _now()
            error = f"{type(exc).__name__}: {exc}"
            records, annual = [], 0
        receipt = dict(
            run_id=run_id,
            url=URL,
            started_at=started.isoformat(),
            received_at=received.isoformat(),
            http_status=status,
            outcome="FAILED" if error else "CAPTURED",
            error=error,
            raw_sha256=digest(raw),
            normalizer_version=VERSION,
            monthly_count=len(records),
            excluded_annual_count=annual,
            mode="CAPTURE_ONLY",
            availability_basis="SYSTEM_OBSERVED",
            citation=DISCLAIMER,
            retrieval_date=received.date().isoformat(),
        )
        (stage / "response.bin").write_bytes(raw)
        (stage / "records.jsonl").touch()
        store = AppendOnlyRecordStore[MacroRecord](
            stage / "records.jsonl",
            id_of=lambda r: r.record_id,
            to_dict=record_dict,
            from_dict=lambda d: next(r for r in records if r.record_id == d["record_id"]),
        )
        for record in records:
            store.record(record)
        (stage / "receipt.json").write_bytes(encode(receipt))
        (stage / "manifest.json").write_bytes(
            encode({name: digest((stage / name).read_bytes()) for name in ("response.bin", "receipt.json", "records.jsonl")})
        )
        stage.rename(final)
        return show(root, run_id)
