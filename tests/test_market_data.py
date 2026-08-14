from unittest.mock import MagicMock, patch

import pytest

from core.models import Market
from core.providers.market_data import ProviderError, fetch_snapshot, infer_market, normalize_symbol


def test_infer_market_detects_jp_code():
    assert infer_market("7203") == Market.JP


def test_infer_market_detects_us_ticker():
    assert infer_market("AAPL") == Market.US


def test_normalize_symbol_appends_suffix_for_jp():
    assert normalize_symbol("7203", Market.JP) == "7203.T"


def test_normalize_symbol_does_not_double_suffix():
    assert normalize_symbol("7203.T", Market.JP) == "7203.T"


def test_normalize_symbol_us_unchanged():
    assert normalize_symbol("AAPL", Market.US) == "AAPL"


def _mock_ticker(info: dict, financials=None):
    ticker = MagicMock()
    ticker.info = info
    ticker.financials = financials if financials is not None else MagicMock(empty=True)
    return ticker


@patch("yfinance.Ticker")
def test_fetch_snapshot_maps_fields(mock_ticker_cls):
    info = {
        "currentPrice": 2500.0,
        "currency": "JPY",
        "trailingPE": 15.0,
        "priceToBook": 1.2,
        "returnOnEquity": 0.15,
        "dividendYield": 2.5,  # パーセント表記 -> 0.025に正規化されるはず
        "marketCap": 30_000_000_000,
        "fiftyTwoWeekHigh": 3000.0,
        "fiftyTwoWeekLow": 2000.0,
        "sector": "Consumer Cyclical",
        "industry": "Auto Manufacturers",
        "longName": "Toyota Motor Corp",
    }
    mock_ticker_cls.return_value = _mock_ticker(info)

    snapshot = fetch_snapshot("7203", Market.JP)

    assert snapshot.price == 2500.0
    assert snapshot.dividend_yield == pytest.approx(0.025)
    assert snapshot.name == "Toyota Motor Corp"
    assert snapshot.source == "yfinance"


@patch("yfinance.Ticker")
def test_fetch_snapshot_handles_sub_1pct_dividend_and_high_roe(mock_ticker_cls):
    # 実際のAAPLレスポンス(2026-08時点)を再現した回帰テスト。
    # dividendYield=0.36 は「0.36%」を意味し(dividendRate 1.08 / price 305.26 で検算済み)、
    # returnOnEquity=1.4875 は既に比率(148.75%、自社株買いの影響で100%超)であり変換不要。
    info = {
        "currentPrice": 305.26,
        "currency": "USD",
        "trailingPE": 34.93,
        "priceToBook": 41.48,
        "returnOnEquity": 1.4875101,
        "dividendYield": 0.36,
        "dividendRate": 1.08,
        "marketCap": 4_455_019_315_200,
        "longName": "Apple Inc.",
    }
    mock_ticker_cls.return_value = _mock_ticker(info)

    snapshot = fetch_snapshot("AAPL", Market.US)

    assert snapshot.dividend_yield == pytest.approx(0.0036)
    assert snapshot.roe == pytest.approx(1.4875101)


@patch("yfinance.Ticker")
def test_fetch_snapshot_raises_when_not_found(mock_ticker_cls):
    mock_ticker_cls.return_value = _mock_ticker({})
    with pytest.raises(ProviderError):
        fetch_snapshot("0000", Market.JP)


@patch("yfinance.Ticker")
def test_fetch_snapshot_wraps_network_errors(mock_ticker_cls):
    ticker = MagicMock()
    type(ticker).info = property(lambda self: (_ for _ in ()).throw(ConnectionError("boom")))
    mock_ticker_cls.return_value = ticker

    with pytest.raises(ProviderError):
        fetch_snapshot("AAPL", Market.US)
