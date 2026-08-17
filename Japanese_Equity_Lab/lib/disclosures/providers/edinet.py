"""EDINET API V2 への未検証の一次接続(Phase4B-2)。

**この時点でField-level実装は一切行わない**(Documents Listの実レスポンス
スキーマ・Document Downloadの`type`値・認証方式の正確な形、いずれも公式資料への
疎通ができず未確認。`Japanese_Equity_Lab/EDINET_SOURCE_ONBOARDING.md`参照)。
ここで提供するのはRaw HTTPレスポンスをそのまま取得するための最小限のClientのみで
あり、`DisclosureDocument`への正規化(normalize)・`DocumentKind`マッピング・
Entity解決などは一切行わない(それらはField名が確認できるまで意図的に未実装)。

**認証方式は未確認。** 検索により得られた二次情報は「`Subscription-Key`という
クエリパラメータ」を示唆するものと、当初タスク側で仮定していた
「`Ocp-Apim-Subscription-Key`ヘッダ」の両方が存在するが、いずれも一次資料では
確認できていない。`auth_style`引数でどちらを試すか明示的に選べるようにしてある
(既定は`"query_param"`。`EDINET_SOURCE_ONBOARDING.md` §1参照)。

**エンドポイントURLも未確認の候補。** `BASE_URL`は検索結果で繰り返し言及された
`https://api.edinet-fsa.go.jp/api/v2`を候補として採用しているが、本セッションは
このホストへの接続自体がegressポリシーによりブロックされており(`curl`で
`CONNECT tunnel failed, 403`を確認済み)、公式資料はおろか疎通そのものが
検証できていない。

**Document Downloadの`type`パラメータは矛盾する情報しか見つかっていない**
(`EDINET_SOURCE_ONBOARDING.md` §7: 二次資料間で同じ数値が別の形式を指している)。
`fetch_document_raw()`はこの値を必須の明示的引数として要求し、既定値は持たせない
— 呼び出し側が値を推測しないよう強制する設計。

このAdapterが返す`RawFetchResult.request_parameters`には、認証方式にかかわらず
APIキーを一切含めない(`lib.snapshot.RawSnapshotStore`のSecret Leakage Checkとは
独立に、ここでも二重に保証する)。
"""

from __future__ import annotations

import base64
import logging
import os
import time
from datetime import UTC, date, datetime
from typing import Literal

import requests

from lib.data_sources.base import RawFetchResult
from lib.errors import DataSourceError

logger = logging.getLogger(__name__)

BASE_URL = "https://api.edinet-fsa.go.jp/api/v2"
RESPONSE_SCHEMA_VERSION = (
    "edinet-v2(未検証: 公式資料へ疎通不可、二次情報のみ、一部矛盾あり。"
    "Japanese_Equity_Lab/EDINET_SOURCE_ONBOARDING.md参照。実装前に必ず"
    "ローカル環境で実レスポンスを確認すること)"
)

AuthStyle = Literal["query_param", "header"]
_QUERY_PARAM_AUTH_KEY_NAME = "Subscription-Key"
_HEADER_AUTH_KEY_NAME = "Ocp-Apim-Subscription-Key"
# 公式に文書化されたレート制限は未確認(EDINET_SOURCE_ONBOARDING.md §2)。
# 非公式情報(実運用上3〜5秒間隔が必要との言及)に基づく暫定的な安全マージン。
_RATE_LIMIT_INTERVAL_SEC = 5.0


class EdinetAdapter:
    """EDINET API V2 への最小限のRaw HTTP Client(Phase4B-2)。

    Documents List(``/documents.json``)とDocument Download
    (``/documents/{docID}``)のRaw Fetchのみを提供する。Field-level
    Normalizationは一切行わない。`lib.sources.providers.DisclosureProvider`
    Protocolはまだ満たさない — ``fetch_disclosures(codes=...)``によるcode絞り込みには
    確認済みのField名(``secCode``等)が必要なため、Phase4B-2では意図的に未実装。
    """

    def __init__(
        self,
        api_key: str | None = None,
        session: requests.Session | None = None,
        *,
        auth_style: AuthStyle = "query_param",
    ) -> None:
        self._api_key = api_key or os.environ.get("EDINET_API_KEY")
        self._session = session or requests.Session()
        self._auth_style = auth_style
        self._last_request_at: float = 0.0

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def _require_configured(self) -> str:
        if not self._api_key:
            raise DataSourceError("EDINET_API_KEY が設定されていません(.envを確認してください)")
        return self._api_key

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < _RATE_LIMIT_INTERVAL_SEC:
            time.sleep(_RATE_LIMIT_INTERVAL_SEC - elapsed)

    def _request(self, endpoint: str, recorded_params: dict[str, str], *, error_label: str) -> requests.Response:
        """認証情報を含めたHTTPリクエストを実行するが、`recorded_params`
        (Snapshotへそのまま記録される側)には認証情報を一切含めない。"""
        api_key = self._require_configured()
        outgoing_params = dict(recorded_params)
        headers: dict[str, str] = {}
        if self._auth_style == "query_param":
            outgoing_params[_QUERY_PARAM_AUTH_KEY_NAME] = api_key
        else:
            headers[_HEADER_AUTH_KEY_NAME] = api_key

        self._throttle()
        try:
            resp = self._session.get(f"{BASE_URL}{endpoint}", params=outgoing_params, headers=headers, timeout=30)
            self._last_request_at = time.monotonic()
            resp.raise_for_status()
        except requests.RequestException as exc:
            # query_param認証方式の場合、requestsのRequestExceptionはリクエストURL
            # (APIキーを含む)を保持しうる。呼び出し元へ伝播するメッセージは種類名の
            # みとし、原例外はchainしない(exc自体をログにも出力しない)。
            raise DataSourceError(f"{error_label}の取得に失敗しました({type(exc).__name__})") from None
        return resp

    def fetch_documents_list_raw(self, target_date: date, *, list_type: int = 2) -> RawFetchResult:
        """``GET /documents.json``: 指定日のDocuments Listを未加工のまま取得する。

        `date`/`type`という候補パラメータ名は未確認(EDINET_SOURCE_ONBOARDING.md §8)。
        1回の呼び出しにつき1日のみ(日付範囲・銘柄コードによるクエリが可能かは未確認、
        そのため本メソッドにcodes/date-range引数は持たせていない)。
        """
        recorded_params = {"date": target_date.isoformat(), "type": str(list_type)}
        resp = self._request("/documents.json", recorded_params, error_label="EDINET Documents List")
        try:
            body = resp.json()
        except ValueError as exc:
            raise DataSourceError("EDINET Documents Listのレスポンスが JSON として解釈できません") from exc
        return RawFetchResult(
            source="EDINET",
            endpoint="/documents.json",
            request_parameters=recorded_params,
            retrieved_at=datetime.now(UTC),
            data_period=target_date.isoformat(),
            response_schema_version=RESPONSE_SCHEMA_VERSION,
            payload=body,
        )

    def fetch_document_raw(self, source_document_id: str, *, download_type: int) -> RawFetchResult:
        """``GET /documents/{docID}``: 指定書類のダウンロード(スモークテスト用)。

        `download_type`(`type`パラメータ)の値と意味は情報源間で矛盾しており
        (EDINET_SOURCE_ONBOARDING.md §7)、既定値は持たせない — 呼び出し側が
        明示的に値を選ぶことを強制する。

        レスポンスは通常バイナリ(ZIP等)と想定されるため、`RawFetchResult.payload`は
        `lib.snapshot.RawSnapshotStore`(JSON保存)と互換になるよう
        ``{"content_base64": ..., "content_type": ...}`` の形でBase64エンコードして
        保持する(base64は可逆でありByte-for-Byteの整合性を保つ。Content自体の
        解析・展開は一切行わない)。
        """
        recorded_params = {"type": str(download_type)}
        resp = self._request(f"/documents/{source_document_id}", recorded_params, error_label="EDINET Document Download")
        payload = {
            "content_base64": base64.b64encode(resp.content).decode("ascii"),
            "content_type": resp.headers.get("Content-Type"),
        }
        return RawFetchResult(
            source="EDINET",
            endpoint=f"/documents/{source_document_id}",
            request_parameters=recorded_params,
            retrieved_at=datetime.now(UTC),
            data_period=source_document_id,
            response_schema_version=RESPONSE_SCHEMA_VERSION,
            payload=payload,
        )


__all__ = ["EdinetAdapter", "BASE_URL", "RESPONSE_SCHEMA_VERSION"]
