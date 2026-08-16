from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
import requests
from lib.data_sources.convert import daily_quotes_payload_to_raw_bars, trading_calendar_payload_to_calendar
from lib.data_sources.fixture import FixtureDataSourceAdapter
from lib.data_sources.jquants import JQuantsAdapter
from lib.errors import DataSourceError
from lib.market_calendar import TradingCalendarResolutionError

_FIXTURE_PAYLOAD = {
    "daily_quotes": {
        "7203": [
            {"Code": "7203", "Date": "2026-01-05", "Open": 2000, "High": 2010, "Low": 1990, "Close": 2005, "Volume": 1000},
            {"Code": "7203", "Date": "2026-01-06", "Open": 2005, "High": 2020, "Low": 2000, "Close": 2015, "Volume": 1100},
        ]
    },
    "trading_calendar": [
        {"Date": "2026-01-04", "HolidayDivision": "0"},  # 休場(架空)
        {"Date": "2026-01-05", "HolidayDivision": "1"},
        {"Date": "2026-01-06", "HolidayDivision": "1"},
    ],
}


@pytest.fixture
def fixture_path(tmp_path: Path) -> Path:
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(_FIXTURE_PAYLOAD), encoding="utf-8")
    return path


def test_fixture_adapter_fetch_daily_quotes_filters_by_date(fixture_path: Path) -> None:
    adapter = FixtureDataSourceAdapter(fixture_path)
    result = adapter.fetch_daily_quotes(codes=["7203"], start_date=date(2026, 1, 5), end_date=date(2026, 1, 5))
    assert result.source == "fixture"
    assert len(result.payload) == 1
    assert result.payload[0]["Date"] == "2026-01-05"
    assert result.request_parameters == {"codes": ["7203"], "from": "2026-01-05", "to": "2026-01-05"}


def test_fixture_adapter_fetch_trading_calendar(fixture_path: Path) -> None:
    adapter = FixtureDataSourceAdapter(fixture_path)
    result = adapter.fetch_trading_calendar(start_date=date(2026, 1, 4), end_date=date(2026, 1, 6))
    assert len(result.payload) == 3


def test_daily_quotes_payload_to_raw_bars_treats_missing_as_none() -> None:
    payload = [
        {"Code": "7203", "Date": "2026-01-05", "Open": 2000, "High": 2010, "Low": 1990, "Close": 2005, "Volume": 1000},
        {"Code": "7203", "Date": "2026-01-06", "Open": "-", "High": None, "Low": "", "Close": 2015, "Volume": 1100},
    ]
    bars = daily_quotes_payload_to_raw_bars(payload)
    assert bars[0].close == 2005
    assert bars[1].open is None  # "-"は推測で埋めずNone(取得不可)
    assert bars[1].high is None
    assert bars[1].low is None
    assert bars[1].close == 2015


def test_trading_calendar_payload_to_calendar_only_keeps_business_days() -> None:
    calendar = trading_calendar_payload_to_calendar(
        _FIXTURE_PAYLOAD["trading_calendar"], range_start=date(2026, 1, 4), range_end=date(2026, 1, 6)
    )
    assert calendar.is_trading_session(date(2026, 1, 4)) is False
    assert calendar.is_trading_session(date(2026, 1, 5)) is True
    with pytest.raises(TradingCalendarResolutionError):
        calendar.is_trading_session(date(2026, 1, 10))


def test_jquants_adapter_unconfigured_raises_data_source_error_without_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JQUANTS_REFRESH_TOKEN", raising=False)
    adapter = JQuantsAdapter(refresh_token=None)
    assert adapter.configured is False
    with pytest.raises(DataSourceError, match="JQUANTS_REFRESH_TOKEN"):
        adapter.fetch_daily_quotes(codes=["7203"], start_date=date(2026, 1, 1), end_date=date(2026, 1, 31))


def test_jquants_adapter_auth_failure_does_not_leak_refresh_token_in_exception() -> None:
    """認証失敗時の例外メッセージにrefresh_tokenの値が含まれないことを確認する。"""
    secret_token = "super-secret-refresh-token-xyz"
    adapter = JQuantsAdapter(refresh_token=secret_token)

    class _FailingSession:
        def post(self, *args: object, **kwargs: object) -> None:
            raise requests.exceptions.ConnectionError(f"failed to connect (params={kwargs.get('params')})")

    adapter._session = _FailingSession()  # type: ignore[assignment]

    with pytest.raises(DataSourceError) as excinfo:
        adapter.fetch_daily_quotes(codes=["7203"], start_date=date(2026, 1, 1), end_date=date(2026, 1, 31))

    assert secret_token not in str(excinfo.value)
    assert excinfo.value.__cause__ is None  # `from None` でchainを断ち切っている
