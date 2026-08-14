"""Finnhub API から米国株のアナリスト予想(EPS/売上高)を取得するクライアント。

無料枠: 60コール/分。国際銘柄の詳細データは有料プランが必要な場合がある。

重要: `/stock/eps-estimate` `/stock/revenue-estimate` のレスポンス形式は公式
ドキュメントに基づく想定であり、このサンドボックス環境からは実際のレスポンスを
確認できていない。本番投入前に必ず `scripts/check_provider.py` で実レスポンスを
確認し、フィールド名が異なる場合はこのファイルを実際のレスポンスに合わせて
修正すること。
"""

from __future__ import annotations

import logging
import os
from datetime import date

import requests

from core.errors import ProviderError
from core.models import ForecastLabel, ForecastSnapshot, ForecastValue, Market

logger = logging.getLogger(__name__)

BASE_URL = "https://finnhub.io/api/v1"


class FinnhubClient:
    """Finnhub APIクライアント。APIキーはコンストラクタ引数か環境変数
    ``FINNHUB_API_KEY`` から取得する。"""

    def __init__(self, api_key: str | None = None, session: requests.Session | None = None):
        self.api_key = api_key or os.environ.get("FINNHUB_API_KEY")
        self._session = session or requests.Session()

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _get(self, path: str, params: dict) -> dict:
        try:
            resp = self._session.get(
                f"{BASE_URL}{path}",
                params={**params, "token": self.api_key},
                timeout=15,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise ProviderError(f"Finnhub API呼び出しに失敗しました ({path}): {exc}") from exc
        return resp.json()

    def get_forecast(self, ticker: str) -> ForecastSnapshot:
        """指定ティッカーのアナリストEPS/売上高コンセンサス予想を取得する。"""
        if not self.configured:
            return ForecastSnapshot(
                code=ticker,
                market=Market.US,
                values=[
                    ForecastValue.unavailable("EPS予想(四半期)", "FINNHUB_API_KEY未設定"),
                    ForecastValue.unavailable("売上高予想(四半期)", "FINNHUB_API_KEY未設定"),
                ],
            )

        values: list[ForecastValue] = []
        values.append(self._fetch_estimate(ticker, "/stock/eps-estimate", "epsAvg", "EPS予想(四半期)"))
        values.append(self._fetch_estimate(ticker, "/stock/revenue-estimate", "revenueAvg", "売上高予想(四半期)"))
        return ForecastSnapshot(code=ticker, market=Market.US, values=values)

    def _fetch_estimate(self, ticker: str, path: str, value_key: str, label: str) -> ForecastValue:
        try:
            payload = self._get(path, {"symbol": ticker, "freq": "quarterly"})
        except ProviderError as exc:
            logger.warning("finnhub estimate fetch failed: %s", exc)
            return ForecastValue.unavailable(label, str(exc))

        data = payload.get("data") or []
        if not data:
            return ForecastValue.unavailable(label, "コンセンサスデータなし")

        # 直近の対象期間(period)のレコードを採用する
        latest = sorted(data, key=lambda d: d.get("period", ""))[-1]
        raw_value = latest.get(value_key)
        if raw_value is None:
            return ForecastValue.unavailable(label, "対象フィールドが見つかりません")

        return ForecastValue(
            metric=label,
            value=float(raw_value),
            label=ForecastLabel.ANALYST_CONSENSUS,
            source="Finnhub (アナリストコンセンサス)",
            source_url="https://finnhub.io/",
            as_of=latest.get("period") or str(date.today()),
        )
