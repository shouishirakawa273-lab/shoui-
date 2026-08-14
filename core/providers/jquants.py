"""J-Quants API (日本取引所グループ) から会社業績予想を取得するクライアント。

無料プランは以下の制約がある(2026年時点でユーザーが把握している内容。実際の
仕様は変更される可能性があるため、`scripts/check_provider.py` で必ず疎通確認
すること):

- データに約12週間の遅延がある
- レート制限は5リクエスト/分 -> `_RATE_LIMIT_INTERVAL_SEC` でリクエスト間隔を確保する
- 認証はリフレッシュトークン -> IDトークンの2段階

重要: フィールド名(ForecastNetSales等)はJ-Quants公式ドキュメントに基づく想定
であり、このサンドボックス環境からは実際のレスポンスを確認できていない。
本番投入前に必ず `scripts/check_provider.py` で実レスポンスを確認し、
フィールド名が異なる場合は `_STATEMENT_FIELD_MAP` を実際のレスポンスに合わせて
修正すること。
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta

import requests

from core.errors import ProviderError
from core.models import ForecastLabel, ForecastSnapshot, ForecastValue, Market

logger = logging.getLogger(__name__)

BASE_URL = "https://api.jquants.com/v1"
_RATE_LIMIT_INTERVAL_SEC = 12.5  # 5リクエスト/分 = 12秒間隔を安全マージン込みで確保

# (JSONのキー, 表示メトリック名, 予想ラベル)
# 実績値: NetSales / OperatingProfit / Profit
# 今期会社予想: ForecastNetSales / ForecastOperatingProfit / ForecastProfit / ForecastEarningsPerShare
# 来期会社予想: NextYearForecastNetSales / NextYearForecastOperatingProfit / NextYearForecastProfit
_STATEMENT_FIELD_MAP = [
    ("ForecastNetSales", "今期売上高予想", ForecastLabel.COMPANY_GUIDANCE),
    ("ForecastOperatingProfit", "今期営業利益予想", ForecastLabel.COMPANY_GUIDANCE),
    ("ForecastProfit", "今期純利益予想", ForecastLabel.COMPANY_GUIDANCE),
    ("ForecastEarningsPerShare", "今期EPS予想", ForecastLabel.COMPANY_GUIDANCE),
    ("NextYearForecastNetSales", "来期売上高予想", ForecastLabel.COMPANY_GUIDANCE),
    ("NextYearForecastOperatingProfit", "来期営業利益予想", ForecastLabel.COMPANY_GUIDANCE),
    ("NextYearForecastProfit", "来期純利益予想", ForecastLabel.COMPANY_GUIDANCE),
]


class JQuantsClient:
    """J-Quants APIクライアント。リフレッシュトークンはコンストラクタ引数か
    環境変数 ``JQUANTS_REFRESH_TOKEN`` から取得する。"""

    def __init__(self, refresh_token: str | None = None, session: requests.Session | None = None):
        self.refresh_token = refresh_token or os.environ.get("JQUANTS_REFRESH_TOKEN")
        self._session = session or requests.Session()
        self._id_token: str | None = None
        self._id_token_expiry: datetime | None = None
        self._last_request_at: float = 0.0

    @property
    def configured(self) -> bool:
        return bool(self.refresh_token)

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < _RATE_LIMIT_INTERVAL_SEC:
            time.sleep(_RATE_LIMIT_INTERVAL_SEC - elapsed)

    def _authenticate(self) -> str:
        if self._id_token and self._id_token_expiry and datetime.now() < self._id_token_expiry:
            return self._id_token
        if not self.refresh_token:
            raise ProviderError("JQUANTS_REFRESH_TOKEN が設定されていません")
        try:
            self._throttle()
            resp = self._session.post(
                f"{BASE_URL}/token/auth_refresh",
                params={"refreshtoken": self.refresh_token},
                timeout=15,
            )
            self._last_request_at = time.monotonic()
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise ProviderError(f"J-Quants認証に失敗しました: {exc}") from exc

        data = resp.json()
        id_token = data.get("idToken")
        if not id_token:
            raise ProviderError(f"J-Quants認証レスポンスにidTokenが含まれていません: {data}")
        self._id_token = id_token
        self._id_token_expiry = datetime.now() + timedelta(hours=23)  # 実際の有効期限に合わせて調整すること
        return id_token

    def get_forecast(self, code: str) -> ForecastSnapshot:
        """指定銘柄(証券コード)の直近の決算短信ベース業績予想を取得する。"""
        if not self.configured:
            return ForecastSnapshot(
                code=code,
                market=Market.JP,
                values=[ForecastValue.unavailable(label, "JQUANTS_REFRESH_TOKEN未設定") for _, label, _ in _STATEMENT_FIELD_MAP],
            )

        try:
            id_token = self._authenticate()
            self._throttle()
            resp = self._session.get(
                f"{BASE_URL}/fins/statements",
                params={"code": code},
                headers={"Authorization": f"Bearer {id_token}"},
                timeout=15,
            )
            self._last_request_at = time.monotonic()
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise ProviderError(f"{code} の業績予想取得に失敗しました: {exc}") from exc

        payload = resp.json()
        statements = payload.get("statements", [])
        if not statements:
            return ForecastSnapshot(
                code=code,
                market=Market.JP,
                values=[ForecastValue.unavailable(label, "開示データなし") for _, label, _ in _STATEMENT_FIELD_MAP],
            )

        # DisclosedDate が最も新しいものを採用する
        latest = max(statements, key=lambda s: s.get("DisclosedDate", ""))
        as_of = latest.get("DisclosedDate")
        values = []
        for json_key, label, forecast_label in _STATEMENT_FIELD_MAP:
            raw = latest.get(json_key)
            if raw in (None, "", "-"):
                values.append(ForecastValue.unavailable(label, "当該項目は未開示"))
                continue
            try:
                numeric_value = float(raw)
            except (TypeError, ValueError):
                logger.warning("J-Quants field %s could not be parsed as float: %r", json_key, raw)
                values.append(ForecastValue.unavailable(label, "数値として解釈できませんでした"))
                continue
            values.append(
                ForecastValue(
                    metric=label,
                    value=numeric_value,
                    label=forecast_label,
                    source="J-Quants (会社発表)",
                    source_url="https://jpx-jquants.com/",
                    as_of=as_of,
                )
            )
        return ForecastSnapshot(code=code, market=Market.JP, values=values)
