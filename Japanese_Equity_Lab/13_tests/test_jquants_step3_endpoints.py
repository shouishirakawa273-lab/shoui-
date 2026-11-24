"""Step 3 Stage 2: `/equities/valuation` と `/fins/earnings-date` のテスト。

**実APIには接続しない。** HTTPレスポンスは `_RecordingSession` でモックする
(`13_tests/test_data_sources.py` と同じ方式)。

レスポンス形状は2026-11-24に7203と89510で観測した実データに合わせている
(`JQUANTS_V2_STEP3_SOURCE_ONBOARDING.md` §16)。
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from lib.data_sources.jquants import JQuantsAdapter
from lib.errors import DataSourceError

# 7203の最新行(実観測)。
_VALUATION_SHARE_ROW: dict[str, Any] = {
    "Date": "2026-11-20",
    "Code": "72030",
    "EPS": 344.11,
    "FwdEPS": 303.1,
    "BPS": 3179.34,
    "ROE": 0.1151,
    "FwdROE": 0.0953,
    "PER": 9.62,
    "FwdPER": 10.93,
    "PBR": 1.04,
    "MktCap": 39009555.0,
}

# 89510の最新行(実観測)。MktCap以外すべてnull。
_VALUATION_REIT_ROW: dict[str, Any] = {
    "Date": "2026-11-20",
    "Code": "89510",
    "EPS": None,
    "FwdEPS": None,
    "BPS": None,
    "ROE": None,
    "FwdROE": None,
    "PER": None,
    "FwdPER": None,
    "PBR": None,
    "MktCap": 1054274.0,
}

# 7203の先頭行(実観測)。
_EARNINGS_DATE_ROW: dict[str, Any] = {
    "PubDate": "2017-01-04",
    "SchDate": "2017-02-06",
    "FQName": "3Q",
    "FYE": "0331",
    "Code": "72030",
    "CoName": "トヨタ自動車",
    "CoNameEn": "TOYOTA MOTOR CORPORATION",
}


class _RecordingSession:
    """`_get_all_pages` が期待する最小のSession。ページングも再現できる。"""

    def __init__(self, pages: list[dict[str, Any]] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._pages = pages or [{"data": [], "pagination_key": None}]
        self._index = 0

    def get(self, url: str, *, params: dict[str, object], headers: dict[str, str], timeout: int) -> object:
        self.calls.append({"url": url, "params": dict(params), "headers": headers})
        page = self._pages[min(self._index, len(self._pages) - 1)]
        self._index += 1

        class _Resp:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, Any]:
                return page

        return _Resp()


def _adapter(session: _RecordingSession) -> JQuantsAdapter:
    return JQuantsAdapter(api_key="test-api-key", session=session)  # type: ignore[arg-type]


# --- /equities/valuation ---


def test_valuation_calls_the_official_endpoint_with_code_only() -> None:
    session = _RecordingSession([{"data": [_VALUATION_SHARE_ROW], "pagination_key": None}])
    result = _adapter(session).fetch_valuation_indicators(codes=["7203"])

    assert len(session.calls) == 1
    assert "/v2/equities/valuation" in str(session.calls[0]["url"])
    assert session.calls[0]["params"] == {"code": "7203"}
    assert result.endpoint == "/v2/equities/valuation"
    assert result.payload == [_VALUATION_SHARE_ROW]


def test_valuation_does_not_send_a_date_range() -> None:
    """期間を送らない。送っていないので、返ったCoverageがそのまま全てになる。"""
    session = _RecordingSession()
    result = _adapter(session).fetch_valuation_indicators(codes=["7203"])
    assert "from" not in session.calls[0]["params"]
    assert "to" not in session.calls[0]["params"]
    assert result.data_period == "full_available_history"


def test_valuation_payload_is_returned_unmodified() -> None:
    """REITのnullを0や欠損に変えない。Rawをそのまま返す。"""
    session = _RecordingSession([{"data": [_VALUATION_REIT_ROW], "pagination_key": None}])
    result = _adapter(session).fetch_valuation_indicators(codes=["8951"])
    row = result.payload[0]
    assert row["MktCap"] == 1054274.0
    for field in ("EPS", "BPS", "ROE", "PER", "PBR"):
        assert row[field] is None


def test_valuation_fetches_each_code_separately() -> None:
    session = _RecordingSession()
    _adapter(session).fetch_valuation_indicators(codes=["7203", "8951"])
    assert [c["params"]["code"] for c in session.calls] == ["7203", "8951"]


def test_valuation_follows_pagination() -> None:
    session = _RecordingSession(
        [
            {"data": [_VALUATION_SHARE_ROW], "pagination_key": "next"},
            {"data": [_VALUATION_REIT_ROW], "pagination_key": None},
        ]
    )
    result = _adapter(session).fetch_valuation_indicators(codes=["7203"])
    assert len(result.payload) == 2
    assert len(session.calls) == 2


def test_valuation_uses_api_key_header() -> None:
    session = _RecordingSession()
    _adapter(session).fetch_valuation_indicators(codes=["7203"])
    assert session.calls[0]["headers"] == {"x-api-key": "test-api-key"}


# --- /fins/earnings-date ---


def test_earnings_dates_calls_the_official_endpoint_with_code_only() -> None:
    session = _RecordingSession([{"data": [_EARNINGS_DATE_ROW], "pagination_key": None}])
    result = _adapter(session).fetch_earnings_dates(codes=["7203"])

    assert "/v2/fins/earnings-date" in str(session.calls[0]["url"])
    assert session.calls[0]["params"] == {"code": "7203"}
    assert result.endpoint == "/v2/fins/earnings-date"
    assert result.payload[0]["SchDate"] == "2017-02-06"
    assert result.payload[0]["PubDate"] == "2017-01-04"


def test_earnings_dates_never_queries_by_scheduled_date() -> None:
    """[PIT] 予定日で引くと、訂正された予定日は現在有効なものしか返らない。

    その経路を使うと「その時点で市場が知っていた予定日」を再現できないので、
    引数としても送信パラメータとしても存在させない。
    """
    session = _RecordingSession()
    adapter = _adapter(session)
    adapter.fetch_earnings_dates(codes=["7203"])
    assert "scheduled_date" not in session.calls[0]["params"]
    assert "SchDate" not in session.calls[0]["params"]

    with pytest.raises(TypeError):
        adapter.fetch_earnings_dates(codes=["7203"], scheduled_date=date(2026, 5, 8))  # type: ignore[call-arg]


def test_earnings_dates_keeps_published_and_scheduled_pairs() -> None:
    """改定履歴は(公表日, 予定日)の対で表される。片方だけに畳まない。"""
    revised = {**_EARNINGS_DATE_ROW, "PubDate": "2017-01-20", "SchDate": "2017-02-13"}
    session = _RecordingSession([{"data": [_EARNINGS_DATE_ROW, revised], "pagination_key": None}])
    result = _adapter(session).fetch_earnings_dates(codes=["7203"])
    pairs = {(r["PubDate"], r["SchDate"]) for r in result.payload}
    assert pairs == {("2017-01-04", "2017-02-06"), ("2017-01-20", "2017-02-13")}


def test_earnings_dates_fetches_each_code_separately() -> None:
    session = _RecordingSession()
    _adapter(session).fetch_earnings_dates(codes=["7203", "8951"])
    assert [c["params"]["code"] for c in session.calls] == ["7203", "8951"]


# --- 認証なし ---


def test_both_endpoints_fail_closed_without_an_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JQUANTS_API_KEY", raising=False)
    adapter = JQuantsAdapter(api_key=None)
    assert adapter.configured is False
    with pytest.raises(DataSourceError, match="JQUANTS_API_KEY"):
        adapter.fetch_valuation_indicators(codes=["7203"])
    with pytest.raises(DataSourceError, match="JQUANTS_API_KEY"):
        adapter.fetch_earnings_dates(codes=["7203"])


def test_no_codes_makes_no_requests() -> None:
    session = _RecordingSession()
    adapter = _adapter(session)
    assert adapter.fetch_valuation_indicators(codes=[]).payload == []
    assert adapter.fetch_earnings_dates(codes=[]).payload == []
    assert session.calls == []
