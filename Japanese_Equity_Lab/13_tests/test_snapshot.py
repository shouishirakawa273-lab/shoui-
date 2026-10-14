from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from lib.data_sources.base import RawFetchResult
from lib.errors import AppendOnlyViolationError
from lib.snapshot import RawSnapshotStore, SecretLeakageError, SnapshotTamperedError


def _fetch_result(**overrides: object) -> RawFetchResult:
    defaults: dict[str, object] = dict(
        source="jquants",
        endpoint="/prices/daily_quotes",
        request_parameters={"code": "7203", "from": "2026-01-01", "to": "2026-01-31"},
        retrieved_at=datetime(2026, 8, 16, 12, 0, tzinfo=UTC),
        data_period="2026-01-01/2026-01-31",
        response_schema_version="jquants-v1-daily_quotes",
        payload=[{"Code": "7203", "Date": "2026-01-05", "Close": 2000}],
    )
    defaults.update(overrides)
    return RawFetchResult(**defaults)  # type: ignore[arg-type]


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    store = RawSnapshotStore(tmp_path / "01_data" / "raw")
    manifest = store.save(_fetch_result(), snapshot_id="SNAP0001")

    assert manifest.record_count == 1
    assert manifest.source == "jquants"

    loaded_manifest, payload = store.load("jquants", "SNAP0001")
    assert loaded_manifest.content_hash == manifest.content_hash
    assert payload == [{"Code": "7203", "Date": "2026-01-05", "Close": 2000}]


def test_duplicate_snapshot_id_is_rejected(tmp_path: Path) -> None:
    store = RawSnapshotStore(tmp_path / "01_data" / "raw")
    store.save(_fetch_result(), snapshot_id="SNAP0001")
    with pytest.raises(AppendOnlyViolationError):
        store.save(_fetch_result(), snapshot_id="SNAP0001")


def test_request_parameters_with_token_like_key_is_rejected(tmp_path: Path) -> None:
    store = RawSnapshotStore(tmp_path / "01_data" / "raw")
    leaking = _fetch_result(request_parameters={"code": "7203", "idToken": "secretsecret"})
    with pytest.raises(SecretLeakageError):
        store.save(leaking, snapshot_id="SNAP0002")


def test_tampered_payload_is_detected_on_load(tmp_path: Path) -> None:
    """保存後にRaw Snapshotのファイルが書き換えられたことをcontent_hashの不一致で検出する。"""
    base_dir = tmp_path / "01_data" / "raw"
    store = RawSnapshotStore(base_dir)
    store.save(_fetch_result(), snapshot_id="SNAP0001")

    payload_path = base_dir / "jquants" / "SNAP0001.json"
    tampered = json.loads(payload_path.read_text(encoding="utf-8"))
    tampered[0]["Close"] = 999999  # 改変
    payload_path.write_text(json.dumps(tampered, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(SnapshotTamperedError):
        store.load("jquants", "SNAP0001")


def test_load_missing_snapshot_raises_file_not_found(tmp_path: Path) -> None:
    store = RawSnapshotStore(tmp_path / "01_data" / "raw")
    with pytest.raises(FileNotFoundError):
        store.load("jquants", "DOES_NOT_EXIST")
