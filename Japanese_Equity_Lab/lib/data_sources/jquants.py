"""J-Quants API の DataSourceAdapter 実装。

認証: リフレッシュトークン(環境変数 ``JQUANTS_REFRESH_TOKEN``、親リポジトリの
`.env` を経由)からIDトークンを取得し、Bearer認証でリクエストする
(`core/providers/jquants.py` と同じ認証フロー)。レート制限(5リクエスト/分)を
守るため、リクエスト間隔を確保する。

重要な既知の制約:
- このAdapterはJ-Quants公式ドキュメントに基づくエンドポイント・フィールド名を
  前提に実装している。**このセッションはネットワークポリシーにより外部APIへの
  疎通が一切できない環境で開発されており、実レスポンスでの検証は行えていない**
  (`README.md` の既知の制約、`scripts/jquants_lab_snapshot.py` 参照)。
  本番投入前に必ずローカル環境で疎通確認し、フィールド名が異なる場合は
  `lib/data_sources/convert.py` を実際のレスポンスに合わせて修正すること。
- 認証情報(リフレッシュトークン・IDトークン)はログ・例外メッセージ・
  Snapshotのいずれにも出力しない。
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta

import requests

from lib.data_sources.base import RawFetchResult
from lib.errors import DataSourceError

logger = logging.getLogger(__name__)

BASE_URL = "https://api.jquants.com/v1"
RESPONSE_SCHEMA_VERSION = "jquants-v1(未検証)"
_RATE_LIMIT_INTERVAL_SEC = 12.5  # 5リクエスト/分を安全マージン込みで確保


class JQuantsAdapter:
    """J-Quants API (日次株価・取引カレンダー) の DataSourceAdapter 実装。

    使用エンドポイント:
    - ``POST /token/auth_refresh``: リフレッシュトークン -> IDトークン
    - ``GET /prices/daily_quotes``: 銘柄別の日次OHLCV(未調整、AdjustmentFactor等を含む)
    - ``GET /markets/trading_calendar``: 取引カレンダー(HolidayDivision等)
    """

    def __init__(self, refresh_token: str | None = None, session: requests.Session | None = None) -> None:
        self._refresh_token = refresh_token or os.environ.get("JQUANTS_REFRESH_TOKEN")
        self._session = session or requests.Session()
        self._id_token: str | None = None
        self._id_token_expiry: datetime | None = None
        self._last_request_at: float = 0.0

    @property
    def configured(self) -> bool:
        return bool(self._refresh_token)

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < _RATE_LIMIT_INTERVAL_SEC:
            time.sleep(_RATE_LIMIT_INTERVAL_SEC - elapsed)

    def _authenticate(self) -> str:
        if self._id_token and self._id_token_expiry and datetime.now() < self._id_token_expiry:
            return self._id_token
        if not self._refresh_token:
            raise DataSourceError("JQUANTS_REFRESH_TOKEN が設定されていません")
        try:
            self._throttle()
            resp = self._session.post(
                f"{BASE_URL}/token/auth_refresh",
                params={"refreshtoken": self._refresh_token},
                timeout=15,
            )
            self._last_request_at = time.monotonic()
            resp.raise_for_status()
        except requests.RequestException:
            # requests例外の文字列表現にはURL(refreshtokenクエリパラメータ込み)が
            # 含まれうるため、chained exceptionとして伝播させない(`from None`)。
            raise DataSourceError("J-Quants認証に失敗しました(詳細はログへ出力しません)") from None

        data = resp.json()
        id_token = data.get("idToken")
        if not id_token:
            raise DataSourceError("J-Quants認証レスポンスにidTokenが含まれていません")
        self._id_token = id_token
        self._id_token_expiry = datetime.now() + timedelta(hours=23)  # 実際の有効期限は要検証
        return id_token

    def fetch_daily_quotes(self, *, codes: Sequence[str], start_date: date, end_date: date) -> RawFetchResult:
        if not self.configured:
            raise DataSourceError("JQUANTS_REFRESH_TOKEN が設定されていません(.envを確認してください)")
        id_token = self._authenticate()

        records: list[dict[str, object]] = []
        for code in codes:
            self._throttle()
            try:
                resp = self._session.get(
                    f"{BASE_URL}/prices/daily_quotes",
                    params={"code": code, "from": start_date.isoformat(), "to": end_date.isoformat()},
                    headers={"Authorization": f"Bearer {id_token}"},
                    timeout=15,
                )
                self._last_request_at = time.monotonic()
                resp.raise_for_status()
            except requests.RequestException as exc:
                raise DataSourceError(f"{code} の日次株価取得に失敗しました: {exc}") from exc
            payload = resp.json()
            records.extend(payload.get("daily_quotes", []))

        return RawFetchResult(
            source="jquants",
            endpoint="/prices/daily_quotes",
            request_parameters={"codes": list(codes), "from": start_date.isoformat(), "to": end_date.isoformat()},
            retrieved_at=datetime.now(UTC),
            data_period=f"{start_date.isoformat()}/{end_date.isoformat()}",
            response_schema_version=RESPONSE_SCHEMA_VERSION,
            payload=records,
        )

    def fetch_trading_calendar(self, *, start_date: date, end_date: date) -> RawFetchResult:
        if not self.configured:
            raise DataSourceError("JQUANTS_REFRESH_TOKEN が設定されていません(.envを確認してください)")
        id_token = self._authenticate()

        self._throttle()
        try:
            resp = self._session.get(
                f"{BASE_URL}/markets/trading_calendar",
                params={"from": start_date.isoformat(), "to": end_date.isoformat()},
                headers={"Authorization": f"Bearer {id_token}"},
                timeout=15,
            )
            self._last_request_at = time.monotonic()
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise DataSourceError(f"取引カレンダー取得に失敗しました: {exc}") from exc

        payload = resp.json()
        records = payload.get("trading_calendar", [])
        return RawFetchResult(
            source="jquants",
            endpoint="/markets/trading_calendar",
            request_parameters={"from": start_date.isoformat(), "to": end_date.isoformat()},
            retrieved_at=datetime.now(UTC),
            data_period=f"{start_date.isoformat()}/{end_date.isoformat()}",
            response_schema_version=RESPONSE_SCHEMA_VERSION,
            payload=records,
        )
