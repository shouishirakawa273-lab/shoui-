from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
import requests
from lib.data_sources.convert import equity_bars_payload_to_raw_bars, trading_calendar_payload_to_calendar
from lib.data_sources.fixture import FixtureDataSourceAdapter
from lib.data_sources.jquants import JQuantsAdapter
from lib.errors import DataSourceError
from lib.market_calendar import TradingCalendarResolutionError

_FIXTURE_PAYLOAD = {
    "equity_bars": {
        "7203": [
            {
                "Code": "7203",
                "Date": "2026-01-05",
                "O": 2000,
                "H": 2010,
                "L": 1990,
                "C": 2005,
                "Vo": 1000,
                "AdjFactor": 1.0,
                "ExRT": None,
            },
            {
                "Code": "7203",
                "Date": "2026-01-06",
                "O": 2005,
                "H": 2020,
                "L": 2000,
                "C": 2015,
                "Vo": 1100,
                "AdjFactor": 1.0,
                "ExRT": None,
            },
        ]
    },
    "trading_calendar": [
        {"Date": "2026-01-04", "HolDiv": "0"},  # 休場(架空)
        {"Date": "2026-01-05", "HolDiv": "1"},
        {"Date": "2026-01-06", "HolDiv": "1"},
    ],
}


@pytest.fixture
def fixture_path(tmp_path: Path) -> Path:
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(_FIXTURE_PAYLOAD), encoding="utf-8")
    return path


def test_fixture_adapter_fetch_equity_bars_filters_by_date(fixture_path: Path) -> None:
    adapter = FixtureDataSourceAdapter(fixture_path)
    result = adapter.fetch_equity_bars(codes=["7203"], start_date=date(2026, 1, 5), end_date=date(2026, 1, 5))
    assert result.source == "fixture"
    assert len(result.payload) == 1
    assert result.payload[0]["Date"] == "2026-01-05"
    assert result.request_parameters == {"codes": ["7203"], "from": "2026-01-05", "to": "2026-01-05"}


def test_fixture_adapter_fetch_trading_calendar(fixture_path: Path) -> None:
    adapter = FixtureDataSourceAdapter(fixture_path)
    result = adapter.fetch_trading_calendar(start_date=date(2026, 1, 4), end_date=date(2026, 1, 6))
    assert len(result.payload) == 3


def test_fixture_adapter_fetch_topix_bars_defaults_to_empty_without_breaking(fixture_path: Path) -> None:
    """topix_barsキーが無いfixtureファイルでも後方互換で空配列を返す。"""
    adapter = FixtureDataSourceAdapter(fixture_path)
    result = adapter.fetch_topix_bars(start_date=date(2026, 1, 1), end_date=date(2026, 1, 31))
    assert result.payload == []


def test_fixture_adapter_fetch_equities_master_defaults_to_empty_without_breaking(fixture_path: Path) -> None:
    adapter = FixtureDataSourceAdapter(fixture_path)
    result = adapter.fetch_equities_master()
    assert result.payload == []


def test_fixture_adapter_capabilities_reports_light_plan_assumption(fixture_path: Path) -> None:
    adapter = FixtureDataSourceAdapter(fixture_path)
    assert adapter.capabilities.daily_prices is True
    assert adapter.capabilities.general_indices is False


def test_jquants_adapter_unconfigured_raises_data_source_error_for_all_endpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JQUANTS_API_KEY", raising=False)
    adapter = JQuantsAdapter(api_key=None)
    assert adapter.configured is False
    with pytest.raises(DataSourceError, match="JQUANTS_API_KEY"):
        adapter.fetch_equity_bars(codes=["7203"], start_date=date(2026, 1, 1), end_date=date(2026, 1, 31))
    with pytest.raises(DataSourceError, match="JQUANTS_API_KEY"):
        adapter.fetch_trading_calendar(start_date=date(2026, 1, 1), end_date=date(2026, 1, 31))
    with pytest.raises(DataSourceError, match="JQUANTS_API_KEY"):
        adapter.fetch_topix_bars(start_date=date(2026, 1, 1), end_date=date(2026, 1, 31))
    with pytest.raises(DataSourceError, match="JQUANTS_API_KEY"):
        adapter.fetch_equities_master()


def test_jquants_adapter_uses_x_api_key_header_not_token_auth() -> None:
    """V2はx-api-key Header認証を使い、V1のtoken/auth_refresh等は一切呼ばない。"""

    class _RecordingSession:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def get(self, url: str, *, params: dict[str, object], headers: dict[str, str], timeout: int) -> object:
            self.calls.append({"url": url, "params": params, "headers": headers})

            class _Resp:
                def raise_for_status(self) -> None:
                    return None

                def json(self) -> dict[str, object]:
                    return {"data": [], "pagination_key": None}

            return _Resp()

    session = _RecordingSession()
    adapter = JQuantsAdapter(api_key="test-api-key", session=session)  # type: ignore[arg-type]
    adapter.fetch_trading_calendar(start_date=date(2026, 1, 1), end_date=date(2026, 1, 31))

    assert len(session.calls) == 1
    call = session.calls[0]
    assert "/v2/markets/calendar" in str(call["url"])
    assert call["headers"] == {"x-api-key": "test-api-key"}
    assert "token" not in str(call["url"])


def test_jquants_adapter_does_not_expose_v1_token_auth_methods() -> None:
    """V1の認証エンドポイント(auth_user/auth_refresh)を呼ぶコードパスが残っていない。

    モジュールdocstring(「V1のこのEndpointは使用しない」という説明文)には該当文字列が
    意図的に出現するため、実装コード(class本体)だけを対象に確認する。
    """
    import inspect

    from lib.data_sources.jquants import BASE_URL, JQuantsAdapter

    source = inspect.getsource(JQuantsAdapter)
    assert "auth_refresh" not in source
    assert "auth_user" not in source
    assert "idToken" not in source
    assert "refresh_token" not in source
    assert BASE_URL == "https://api.jquants.com/v2"


def test_jquants_adapter_follows_pagination_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """pagination_keyが返る限り追加リクエストして全ページを結合する。"""

    class _PaginatingSession:
        def __init__(self) -> None:
            self.call_count = 0

        def get(self, url: str, *, params: dict[str, object], headers: dict[str, str], timeout: int) -> object:
            self.call_count += 1
            page = self.call_count

            class _Resp:
                def raise_for_status(self) -> None:
                    return None

                def json(self) -> dict[str, object]:
                    if page == 1:
                        return {"data": [{"Date": "2026-01-05", "HolDiv": "1"}], "pagination_key": "next-page-token"}
                    return {"data": [{"Date": "2026-01-06", "HolDiv": "1"}], "pagination_key": None}

            return _Resp()

    session = _PaginatingSession()
    adapter = JQuantsAdapter(api_key="test-api-key", session=session)  # type: ignore[arg-type]
    result = adapter.fetch_trading_calendar(start_date=date(2026, 1, 1), end_date=date(2026, 1, 31))

    assert session.call_count == 2
    assert len(result.payload) == 2
    assert [row["Date"] for row in result.payload] == ["2026-01-05", "2026-01-06"]


def test_jquants_adapter_api_key_never_appears_in_request_parameters() -> None:
    """RawFetchResult.request_parameters(Snapshot manifestへそのまま保存される)にAPIキーが
    含まれないことを確認する(Snapshotへの認証情報混入防止)。"""

    class _RecordingSession:
        def get(self, url: str, *, params: dict[str, object], headers: dict[str, str], timeout: int) -> object:
            class _Resp:
                def raise_for_status(self) -> None:
                    return None

                def json(self) -> dict[str, object]:
                    return {"data": [], "pagination_key": None}

            return _Resp()

    secret_key = "super-secret-api-key-xyz"
    adapter = JQuantsAdapter(api_key=secret_key, session=_RecordingSession())  # type: ignore[arg-type]
    result = adapter.fetch_trading_calendar(start_date=date(2026, 1, 1), end_date=date(2026, 1, 31))
    assert secret_key not in json.dumps(result.request_parameters)


def test_equity_bars_payload_to_raw_bars_treats_missing_as_none() -> None:
    payload = [
        {"Code": "7203", "Date": "2026-01-05", "O": 2000, "H": 2010, "L": 1990, "C": 2005, "Vo": 1000},
        {"Code": "7203", "Date": "2026-01-06", "O": "-", "H": None, "L": "", "C": 2015, "Vo": 1100},
    ]
    bars = equity_bars_payload_to_raw_bars(payload)
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


def test_trading_calendar_payload_to_calendar_accepts_explicit_hol_div_override() -> None:
    """HolDivの値の意味が未検証であることを踏まえ、呼び出し側で上書きできることを確認する。"""
    payload = [{"Date": "2026-01-05", "HolDiv": "TRADING"}, {"Date": "2026-01-06", "HolDiv": "CLOSED"}]
    calendar = trading_calendar_payload_to_calendar(
        payload, range_start=date(2026, 1, 5), range_end=date(2026, 1, 6), trading_hol_div_values=frozenset({"TRADING"})
    )
    assert calendar.is_trading_session(date(2026, 1, 5)) is True
    assert calendar.is_trading_session(date(2026, 1, 6)) is False


def test_jquants_adapter_auth_failure_does_not_leak_api_key_in_exception() -> None:
    """認証・通信失敗時の例外メッセージにAPIキーの値が含まれないことを確認する。"""
    secret_key = "super-secret-api-key-xyz"
    adapter = JQuantsAdapter(api_key=secret_key)

    class _FailingSession:
        def get(self, *args: object, **kwargs: object) -> None:
            raise requests.exceptions.ConnectionError(f"failed to connect (params={kwargs.get('params')})")

    adapter._session = _FailingSession()  # type: ignore[assignment]

    with pytest.raises(DataSourceError) as excinfo:
        adapter.fetch_equity_bars(codes=["7203"], start_date=date(2026, 1, 1), end_date=date(2026, 1, 31))

    assert secret_key not in str(excinfo.value)
