from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from lib.data_sources.local_snapshot import LocalSnapshotAdapter
from lib.errors import DataSourceError


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_fetch_equity_bars_reads_json_file_by_naming_convention(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "equity_bars_7203.json",
        {"data": [{"Code": "7203", "Date": "2026-01-05", "O": 2000, "C": 2010, "AdjFactor": 1.0, "ExRT": None}]},
    )
    adapter = LocalSnapshotAdapter(tmp_path)
    result = adapter.fetch_equity_bars(codes=["7203"], start_date=date(2026, 1, 1), end_date=date(2026, 1, 31))
    assert result.source == "jquants_local"
    assert len(result.payload) == 1
    assert result.payload[0]["C"] == 2010


def test_fetch_equity_bars_reads_csv_fallback(tmp_path: Path) -> None:
    csv_path = tmp_path / "equity_bars_6758.csv"
    csv_path.write_text("Code,Date,O,H,L,C,Vo,AdjFactor,ExRT\n6758,2026-01-05,3000,3010,2990,3005,1000,1.0,\n", encoding="utf-8")
    adapter = LocalSnapshotAdapter(tmp_path)
    result = adapter.fetch_equity_bars(codes=["6758"], start_date=date(2026, 1, 1), end_date=date(2026, 1, 31))
    assert result.payload[0]["C"] == "3005"  # CSVは文字列のまま返す(convert.py側でfloat化する)


def test_fetch_equity_bars_raises_clear_error_for_missing_file(tmp_path: Path) -> None:
    adapter = LocalSnapshotAdapter(tmp_path)
    with pytest.raises(DataSourceError, match="9999"):
        adapter.fetch_equity_bars(codes=["9999"], start_date=date(2026, 1, 1), end_date=date(2026, 1, 31))


def test_fetch_trading_calendar_filters_by_date_range(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "trading_calendar.json",
        {
            "data": [
                {"Date": "2026-01-01", "HolDiv": "0"},
                {"Date": "2026-01-05", "HolDiv": "1"},
                {"Date": "2026-02-05", "HolDiv": "1"},
            ]
        },
    )
    adapter = LocalSnapshotAdapter(tmp_path)
    result = adapter.fetch_trading_calendar(start_date=date(2026, 1, 1), end_date=date(2026, 1, 31))
    assert len(result.payload) == 2


def test_fetch_topix_bars_reads_topix_file(tmp_path: Path) -> None:
    _write_json(tmp_path / "topix_bars.json", {"data": [{"Date": "2026-01-05", "C": 2500.0}]})
    adapter = LocalSnapshotAdapter(tmp_path)
    result = adapter.fetch_topix_bars(start_date=date(2026, 1, 1), end_date=date(2026, 1, 31))
    assert result.payload[0]["C"] == 2500.0


def test_fetch_topix_bars_missing_file_raises_clear_error(tmp_path: Path) -> None:
    adapter = LocalSnapshotAdapter(tmp_path)
    with pytest.raises(DataSourceError, match="topix_bars"):
        adapter.fetch_topix_bars(start_date=date(2026, 1, 1), end_date=date(2026, 1, 31))


def test_fetch_general_index_bars_reads_by_index_code(tmp_path: Path) -> None:
    _write_json(tmp_path / "general_index_bars_0040.json", {"data": [{"Date": "2026-01-05", "C": 1500.0}]})
    adapter = LocalSnapshotAdapter(tmp_path)
    result = adapter.fetch_general_index_bars(index_code="0040", start_date=date(2026, 1, 1), end_date=date(2026, 1, 31))
    assert result.payload[0]["C"] == 1500.0


def test_fetch_equities_master_reads_data_key(tmp_path: Path) -> None:
    _write_json(tmp_path / "equities_master.json", {"data": [{"Code": "7203", "CompanyName": "トヨタ自動車"}]})
    adapter = LocalSnapshotAdapter(tmp_path)
    result = adapter.fetch_equities_master()
    assert result.payload[0]["Code"] == "7203"


def test_missing_top_level_data_key_raises_clear_error(tmp_path: Path) -> None:
    """J-Quants V2の生レスポンス(``{"data": [...]}``)をそのまま保存していない場合に
    分かりやすく失敗する。"""
    _write_json(tmp_path / "equities_master.json", {"unexpected_key": []})
    adapter = LocalSnapshotAdapter(tmp_path)
    with pytest.raises(DataSourceError, match="data"):
        adapter.fetch_equities_master()


def test_retrieved_at_defaults_to_file_mtime(tmp_path: Path) -> None:
    path = tmp_path / "equities_master.json"
    _write_json(path, {"data": []})
    adapter = LocalSnapshotAdapter(tmp_path)
    result = adapter.fetch_equities_master()
    # mtimeベースのretrieved_atは「今このテストを実行している時刻」に極めて近いはず。
    from datetime import UTC, datetime

    assert abs((datetime.now(UTC) - result.retrieved_at).total_seconds()) < 60


def test_explicit_retrieved_at_override(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    _write_json(tmp_path / "equities_master.json", {"data": []})
    explicit = datetime(2020, 1, 1, tzinfo=UTC)
    adapter = LocalSnapshotAdapter(tmp_path, retrieved_at=explicit)
    result = adapter.fetch_equities_master()
    assert result.retrieved_at == explicit


def test_missing_snapshot_dir_raises_immediately() -> None:
    with pytest.raises(DataSourceError, match="存在しません"):
        LocalSnapshotAdapter(Path("/nonexistent/path/that/does/not/exist"))


def test_capabilities_reports_light_plan_assumption(tmp_path: Path) -> None:
    adapter = LocalSnapshotAdapter(tmp_path)
    assert adapter.capabilities.topix is True
    assert adapter.capabilities.general_indices is False
