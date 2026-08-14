"""市場に応じて適切な予想データプロバイダを選択するファサード。"""

from __future__ import annotations

from core.models import ForecastSnapshot, Market
from core.providers.finnhub import FinnhubClient
from core.providers.jquants import JQuantsClient


def get_forecast(
    code: str,
    market: Market,
    jquants: JQuantsClient | None = None,
    finnhub: FinnhubClient | None = None,
) -> ForecastSnapshot:
    if market == Market.JP:
        jquants_client = jquants or JQuantsClient()
        return jquants_client.get_forecast(code)
    finnhub_client = finnhub or FinnhubClient()
    return finnhub_client.get_forecast(code)
