from unittest.mock import MagicMock

from core.models import Market
from core.providers.finnhub import FinnhubClient


def test_get_forecast_returns_unavailable_when_not_configured():
    client = FinnhubClient(api_key=None)
    snapshot = client.get_forecast("AAPL")
    assert snapshot.market == Market.US
    assert all(not v.available for v in snapshot.values)


def test_get_forecast_parses_eps_and_revenue_estimates():
    session = MagicMock()

    eps_resp = MagicMock()
    eps_resp.json.return_value = {
        "data": [
            {"period": "2026-06-30", "epsAvg": 1.55},
            {"period": "2026-09-30", "epsAvg": 1.65},
        ]
    }
    eps_resp.raise_for_status.return_value = None

    revenue_resp = MagicMock()
    revenue_resp.json.return_value = {"data": [{"period": "2026-09-30", "revenueAvg": 95_000_000_000}]}
    revenue_resp.raise_for_status.return_value = None

    session.get.side_effect = [eps_resp, revenue_resp]

    client = FinnhubClient(api_key="dummy-key", session=session)
    snapshot = client.get_forecast("AAPL")

    by_metric = {v.metric: v for v in snapshot.values}
    assert by_metric["EPS予想(四半期)"].value == 1.65  # periodが最新のレコードを採用
    assert by_metric["EPS予想(四半期)"].label.value == "アナリスト予想"
    assert by_metric["売上高予想(四半期)"].value == 95_000_000_000


def test_get_forecast_marks_unavailable_when_no_data():
    session = MagicMock()
    empty_resp = MagicMock()
    empty_resp.json.return_value = {"data": []}
    empty_resp.raise_for_status.return_value = None
    session.get.return_value = empty_resp

    client = FinnhubClient(api_key="dummy-key", session=session)
    snapshot = client.get_forecast("AAPL")
    assert all(not v.available for v in snapshot.values)
