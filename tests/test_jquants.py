from unittest.mock import MagicMock

from core.models import Market
from core.providers.jquants import JQuantsClient


def test_get_forecast_returns_unavailable_when_not_configured():
    client = JQuantsClient(refresh_token=None)
    snapshot = client.get_forecast("7203")
    assert snapshot.market == Market.JP
    assert all(not v.available for v in snapshot.values)
    assert all(v.source == "取得不可" for v in snapshot.values)


def test_get_forecast_parses_statement_fields():
    session = MagicMock()
    auth_resp = MagicMock()
    auth_resp.json.return_value = {"idToken": "dummy-token"}
    auth_resp.raise_for_status.return_value = None

    statements_resp = MagicMock()
    statements_resp.json.return_value = {
        "statements": [
            {
                "DisclosedDate": "2026-05-10",
                "ForecastNetSales": "45000000000",
                "ForecastOperatingProfit": "3000000000",
                "ForecastProfit": "2500000000",
                "ForecastEarningsPerShare": "180.5",
                "NextYearForecastNetSales": "-",
            }
        ]
    }
    statements_resp.raise_for_status.return_value = None

    session.post.return_value = auth_resp
    session.get.return_value = statements_resp

    client = JQuantsClient(refresh_token="dummy-refresh", session=session)
    client._throttle = lambda: None  # レート制限待機をテストではスキップ

    snapshot = client.get_forecast("7203")

    by_metric = {v.metric: v for v in snapshot.values}
    assert by_metric["今期売上高予想"].value == 45_000_000_000
    assert by_metric["今期売上高予想"].label.value == "会社予想"
    assert by_metric["今期売上高予想"].as_of == "2026-05-10"
    assert by_metric["来期売上高予想"].available is False


def test_get_forecast_raises_provider_error_on_auth_failure():
    import requests

    session = MagicMock()
    session.post.side_effect = requests.RequestException("network down")

    client = JQuantsClient(refresh_token="dummy-refresh", session=session)
    client._throttle = lambda: None

    from core.errors import ProviderError

    try:
        client.get_forecast("7203")
        assert False, "ProviderError should be raised"
    except ProviderError:
        pass
