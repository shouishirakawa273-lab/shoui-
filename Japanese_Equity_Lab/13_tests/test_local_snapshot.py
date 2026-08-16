from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from lib.data_sources.local_snapshot import LocalSnapshotAdapter
from lib.errors import DataSourceError


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_fetch_daily_quotes_reads_json_file_by_naming_convention(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "daily_quotes_7203.json",
        {"daily_quotes": [{"Code": "7203", "Date": "2026-01-05", "Open": 2000, "Close": 2010}]},
    )
    adapter = LocalSnapshotAdapter(tmp_path)
    result = adapter.fetch_daily_quotes(codes=["7203"], start_date=date(2026, 1, 1), end_date=date(2026, 1, 31))
    assert result.source == "jquants_local"
    assert len(result.payload) == 1
    assert result.payload[0]["Close"] == 2010


def test_fetch_daily_quotes_reads_csv_fallback(tmp_path: Path) -> None:
    csv_path = tmp_path / "daily_quotes_6758.csv"
    csv_path.write_text("Code,Date,Open,High,Low,Close,Volume\n6758,2026-01-05,3000,3010,2990,3005,1000\n", encoding="utf-8")
    adapter = LocalSnapshotAdapter(tmp_path)
    result = adapter.fetch_daily_quotes(codes=["6758"], start_date=date(2026, 1, 1), end_date=date(2026, 1, 31))
    assert result.payload[0]["Close"] == "3005"  # CSVは文字列のまま返す(convert.py側でfloat化する)


def test_fetch_daily_quotes_raises_clear_error_for_missing_file(tmp_path: Path) -> None:
    adapter = LocalSnapshotAdapter(tmp_path)
    with pytest.raises(DataSourceError, match="9999"):
        adapter.fetch_daily_quotes(codes=["9999"], start_date=date(2026, 1, 1), end_date=date(2026, 1, 31))


def test_fetch_trading_calendar_filters_by_date_range(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "trading_calendar.json",
        {
            "trading_calendar": [
                {"Date": "2026-01-01", "HolidayDivision": "0"},
                {"Date": "2026-01-05", "HolidayDivision": "1"},
                {"Date": "2026-02-05", "HolidayDivision": "1"},
            ]
        },
    )
    adapter = LocalSnapshotAdapter(tmp_path)
    result = adapter.fetch_trading_calendar(start_date=date(2026, 1, 1), end_date=date(2026, 1, 31))
    assert len(result.payload) == 2


def test_fetch_index_prices_reads_by_index_code(tmp_path: Path) -> None:
    _write_json(tmp_path / "indices_0000.json", {"indices": [{"Date": "2026-01-05", "Close": 2500.0}]})
    adapter = LocalSnapshotAdapter(tmp_path)
    result = adapter.fetch_index_prices(index_code="0000", start_date=date(2026, 1, 1), end_date=date(2026, 1, 31))
    assert result.payload[0]["Close"] == 2500.0


def test_fetch_index_prices_missing_file_raises_clear_error(tmp_path: Path) -> None:
    adapter = LocalSnapshotAdapter(tmp_path)
    with pytest.raises(DataSourceError, match="indices_0000"):
        adapter.fetch_index_prices(index_code="0000", start_date=date(2026, 1, 1), end_date=date(2026, 1, 31))


def test_fetch_listed_info_reads_info_key(tmp_path: Path) -> None:
    _write_json(tmp_path / "listed_info.json", {"info": [{"Code": "7203", "CompanyName": "Toyota"}]})
    adapter = LocalSnapshotAdapter(tmp_path)
    result = adapter.fetch_listed_info()
    assert result.payload[0]["Code"] == "7203"


def test_missing_top_level_key_raises_clear_error(tmp_path: Path) -> None:
    """J-Quantsの生レスポンスをそのまま保存していない(キーが違う)場合に分かりやすく失敗する。"""
    _write_json(tmp_path / "listed_info.json", {"unexpected_key": []})
    adapter = LocalSnapshotAdapter(tmp_path)
    with pytest.raises(DataSourceError, match="info"):
        adapter.fetch_listed_info()


def test_retrieved_at_defaults_to_file_mtime(tmp_path: Path) -> None:
    path = tmp_path / "listed_info.json"
    _write_json(path, {"info": []})
    adapter = LocalSnapshotAdapter(tmp_path)
    result = adapter.fetch_listed_info()
    # mtimeベースのretrieved_atは「今このテストを実行している時刻」に極めて近いはず。
    from datetime import UTC, datetime

    assert abs((datetime.now(UTC) - result.retrieved_at).total_seconds()) < 60


def test_explicit_retrieved_at_override(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    _write_json(tmp_path / "listed_info.json", {"info": []})
    explicit = datetime(2020, 1, 1, tzinfo=UTC)
    adapter = LocalSnapshotAdapter(tmp_path, retrieved_at=explicit)
    result = adapter.fetch_listed_info()
    assert result.retrieved_at == explicit


def test_missing_snapshot_dir_raises_immediately() -> None:
    with pytest.raises(DataSourceError, match="存在しません"):
        LocalSnapshotAdapter(Path("/nonexistent/path/that/does/not/exist"))
