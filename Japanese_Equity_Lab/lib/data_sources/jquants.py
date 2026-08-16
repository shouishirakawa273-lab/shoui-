"""J-Quants API V2 の DataSourceAdapter 実装。

認証: J-Quants API V2はAPI Key方式。環境変数 ``JQUANTS_API_KEY``(親リポジトリの
`.env` を経由)から取得したキーを ``x-api-key`` Headerに載せてリクエストする。
V1の ``token/auth_user`` / ``token/auth_refresh`` によるリフレッシュトークン/IDトークン
方式は使用しない(Phase3A.1でV1依存を完全に削除、DECISIONS.md D0031参照)。

重要な既知の制約:
- このAdapterはユーザーがセッション内で明示したJ-Quants API V2の仕様(Endpoint・
  Field名)をCanonical Specificationとして実装している。**このセッションは
  ネットワークポリシーにより外部API・J-Quants公式ドキュメントへの疎通が一切できない
  環境で開発されており、実レスポンスでの検証は行えていない**(README.md の
  既知の制約、DECISIONS.md D0031参照)。本番投入前に必ずローカル環境で疎通確認し、
  Field名が異なる場合は`lib/data_sources/convert.py`を実際のレスポンスに合わせて
  修正すること。
- 認証情報(APIキー)はログ・例外メッセージ・Snapshotのいずれにも出力しない。
- 現在の契約プランはLight(ユーザー申告)。`capabilities`(`DataSourceCapabilities`)は
  Lightプランでの利用可否についての未検証の推測を含む。契約プラン上利用できない
  Datasetを、このAdapterが他Providerへsilent fallbackすることはない
  (該当Endpointの呼び出しはそのままJ-Quantsのエラーとして`DataSourceError`に変換される)。
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Sequence
from datetime import UTC, date, datetime

import requests

from lib.data_sources.base import LIGHT_PLAN_ASSUMED, DataSourceCapabilities, RawFetchResult
from lib.errors import DataSourceError

logger = logging.getLogger(__name__)

BASE_URL = "https://api.jquants.com/v2"
RESPONSE_SCHEMA_VERSION = "jquants-v2(未検証、ユーザー提示仕様に基づく実装)"
_RATE_LIMIT_INTERVAL_SEC = 12.5  # レート制限は契約プランにより異なるため、V1同様の安全マージンを暫定的に維持する
_MAX_PAGES = 100  # pagination_keyによる無限ループを避けるための安全弁


class JQuantsAdapter:
    """J-Quants API V2 (日次株価・取引カレンダー・TOPIX・銘柄マスタ) の DataSourceAdapter 実装。

    使用エンドポイント(すべてV2、ユーザー提示のCanonical Specificationに基づく):

    - ``GET /v2/equities/bars/daily``: 個別銘柄の日次Bar(Raw + Adjusted両方を含む)
    - ``GET /v2/markets/calendar``: 取引カレンダー(Date/HolDiv)
    - ``GET /v2/indices/bars/daily/topix``: TOPIX専用の日次価格
    - ``GET /v2/indices/bars/daily``: 一般指数(TOPIX以外、Light plan未確認)
    - ``GET /v2/equities/master``: 銘柄マスタ(上場情報)

    レスポンスは ``{"data": [...], "pagination_key": "..."}`` 形式を前提とし、
    `pagination_key`が返る限り追加リクエストして全ページを結合する。
    """

    def __init__(self, api_key: str | None = None, session: requests.Session | None = None) -> None:
        self._api_key = api_key or os.environ.get("JQUANTS_API_KEY")
        self._session = session or requests.Session()
        self._last_request_at: float = 0.0

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    @property
    def capabilities(self) -> DataSourceCapabilities:
        return LIGHT_PLAN_ASSUMED

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < _RATE_LIMIT_INTERVAL_SEC:
            time.sleep(_RATE_LIMIT_INTERVAL_SEC - elapsed)

    def _require_configured(self) -> str:
        if not self._api_key:
            raise DataSourceError("JQUANTS_API_KEY が設定されていません(.envを確認してください)")
        return self._api_key

    def _get_all_pages(self, endpoint: str, params: dict[str, str], *, error_label: str) -> list[dict[str, object]]:
        api_key = self._require_configured()
        records: list[dict[str, object]] = []
        request_params = dict(params)
        for _ in range(_MAX_PAGES):
            self._throttle()
            try:
                resp = self._session.get(
                    f"{BASE_URL}{endpoint}",
                    params=request_params,
                    headers={"x-api-key": api_key},
                    timeout=15,
                )
                self._last_request_at = time.monotonic()
                resp.raise_for_status()
            except requests.RequestException as exc:
                # requests例外の文字列表現にAPIキーが含まれることは無い(Headerで送っておりURLに
                # 載せていないため)が、念のためchained exceptionにせず要約メッセージのみ伝播する。
                raise DataSourceError(f"{error_label}の取得に失敗しました: {exc}") from exc
            body = resp.json()
            page_records = body.get("data")
            if page_records is None:
                raise DataSourceError(f"{error_label}のレスポンスに'data'キーが見つかりません(V2形式ではない可能性があります)")
            records.extend(page_records)
            pagination_key = body.get("pagination_key")
            if not pagination_key:
                break
            request_params = dict(params)
            request_params["pagination_key"] = pagination_key
        return records

    def fetch_equity_bars(self, *, codes: Sequence[str], start_date: date, end_date: date) -> RawFetchResult:
        records: list[dict[str, object]] = []
        for code in codes:
            records.extend(
                self._get_all_pages(
                    "/equities/bars/daily",
                    {"code": code, "from": start_date.isoformat(), "to": end_date.isoformat()},
                    error_label=f"{code} の日次Bar",
                )
            )
        return RawFetchResult(
            source="jquants",
            endpoint="/v2/equities/bars/daily",
            request_parameters={"codes": list(codes), "from": start_date.isoformat(), "to": end_date.isoformat()},
            retrieved_at=datetime.now(UTC),
            data_period=f"{start_date.isoformat()}/{end_date.isoformat()}",
            response_schema_version=RESPONSE_SCHEMA_VERSION,
            payload=records,
        )

    def fetch_trading_calendar(self, *, start_date: date, end_date: date) -> RawFetchResult:
        params = {"from": start_date.isoformat(), "to": end_date.isoformat()}
        records = self._get_all_pages("/markets/calendar", params, error_label="取引カレンダー")
        return RawFetchResult(
            source="jquants",
            endpoint="/v2/markets/calendar",
            request_parameters=params,
            retrieved_at=datetime.now(UTC),
            data_period=f"{start_date.isoformat()}/{end_date.isoformat()}",
            response_schema_version=RESPONSE_SCHEMA_VERSION,
            payload=records,
        )

    def fetch_topix_bars(self, *, start_date: date, end_date: date) -> RawFetchResult:
        params = {"from": start_date.isoformat(), "to": end_date.isoformat()}
        records = self._get_all_pages("/indices/bars/daily/topix", params, error_label="TOPIX日次価格")
        return RawFetchResult(
            source="jquants",
            endpoint="/v2/indices/bars/daily/topix",
            request_parameters=params,
            retrieved_at=datetime.now(UTC),
            data_period=f"{start_date.isoformat()}/{end_date.isoformat()}",
            response_schema_version=RESPONSE_SCHEMA_VERSION,
            payload=records,
        )

    def fetch_general_index_bars(self, *, index_code: str, start_date: date, end_date: date) -> RawFetchResult:
        """TOPIX以外の一般指数(Light plan未確認、既定のPipelineでは呼び出さない)。"""
        params = {"code": index_code, "from": start_date.isoformat(), "to": end_date.isoformat()}
        records = self._get_all_pages("/indices/bars/daily", params, error_label=f"指数({index_code})")
        return RawFetchResult(
            source="jquants",
            endpoint="/v2/indices/bars/daily",
            request_parameters=params,
            retrieved_at=datetime.now(UTC),
            data_period=f"{start_date.isoformat()}/{end_date.isoformat()}",
            response_schema_version=RESPONSE_SCHEMA_VERSION,
            payload=records,
        )

    def fetch_equities_master(self, *, as_of: date | None = None) -> RawFetchResult:
        params: dict[str, str] = {}
        if as_of is not None:
            params["date"] = as_of.isoformat()
        records = self._get_all_pages("/equities/master", params, error_label="銘柄マスタ")
        return RawFetchResult(
            source="jquants",
            endpoint="/v2/equities/master",
            request_parameters=dict(params),
            retrieved_at=datetime.now(UTC),
            data_period=(as_of.isoformat() if as_of else "current"),
            response_schema_version=RESPONSE_SCHEMA_VERSION,
            payload=records,
        )
