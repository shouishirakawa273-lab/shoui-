"""EDINET API V2 への接続(Phase4B-2、D0046)。

**Local Real Data Validation完了(2026-08-17、ユーザーのローカル環境から)**。
以下はローカル実データ観測 + 公式仕様(EDINET API仕様書 Version 2、金融庁
企画市場局企業開示課)に基づき確認済み:

- Base URL(``https://api.edinet-fsa.go.jp/api/v2``)・認証方式
  (``Subscription-Key``クエリパラメータ)は実際に到達・認証成功を確認済み。
- Documents List(``GET /documents.json``、``date``/``type``パラメータ)は
  実際に`metadata.status="200"`・`metadata.resultset.count`付きレスポンスを
  観測済み。
- Document Download(``GET /documents/{docID}``)の``type``パラメータは
  ユーザーがローカルで参照した公式仕様書の記述として1〜5の意味を得たが、
  実際にDownloadして観測したのは``type=1``(提出本文書及び監査報告書)のみ
  (`Content-Type: application/octet-stream`・ZIPマジックバイト`50 4b 03 04`
  を観測、仕様の記述と一致)。``type=2〜5``は仕様書の記述をそのまま反映した
  ものであり、この Session/Repository自身は一度もDownloadを試みていない
  (`EdinetDownloadType`のDocstring参照、skeptic-reviewer Finding、
  D0046追記)。

**それでもなお未確認/未実装のまま残っている項目**(詳細は
`Japanese_Equity_Lab/EDINET_SOURCE_ONBOARDING.md`・`DECISIONS.md` D0046参照):

- Documents Listが日付範囲・銘柄コードによる直接クエリに対応しているかは
  依然未確認(1回の呼び出しにつき1日、というAdapter設計は維持)。
- **EDINETの過去日付のDocuments Listは日次更新され、後から書き換わりうる**
  (縦覧期間満了・取下げ・書類情報修正等により、`date=2024-05-08`を今取得しても、
  それが2024-05-08時点で実際に観測可能だった内容と同一である保証はない)。
  このAdapter/Normalizerは現在時点のRetrievalしか行わず、Historical PIT
  Snapshotの再構成を主張しない(過去に実際に保存されたImmutable Snapshotが
  無い限り、Historical Point-in-Timeの完全性は達成できない — 既知の
  Source固有の制約であり、Architecture上のBugではない)。

**重要なエラー処理上の注意**: EDINET APIはエラー時もHTTP Status 200を返し、
実際のStatusはJSON Body内の``metadata.status``フィールドに埋め込まれる
(ローカル検証で`StatusCode=401`相当のエラーが`metadata.status="401"`という
形でHTTP 200のJSONとして返ってくることを確認済み)。したがって
``requests.Response.raise_for_status()``だけでは検知できず、本モジュールは
`metadata.status`とレスポンス構造そのものを明示的に検証する。

このAdapterが返す`RawFetchResult.request_parameters`には、認証方式に
かかわらずAPIキーを一切含めない。
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import time
from datetime import UTC, date, datetime
from enum import IntEnum
from typing import Any, Literal

import requests

from lib.data_sources.base import RawFetchResult
from lib.errors import DataSourceError

logger = logging.getLogger(__name__)

BASE_URL = "https://api.edinet-fsa.go.jp/api/v2"
RESPONSE_SCHEMA_VERSION = (
    "edinet-v2(2026-08-17ローカル実データ検証済み: Documents List/Document "
    "Downloadの疎通・認証・エラー形状を確認。Field-level意味論は一部のみ確認 — "
    "Japanese_Equity_Lab/EDINET_SOURCE_ONBOARDING.md参照)"
)

AuthStyle = Literal["query_param", "header"]
_QUERY_PARAM_AUTH_KEY_NAME = "Subscription-Key"
_HEADER_AUTH_KEY_NAME = "Ocp-Apim-Subscription-Key"
# 公式に文書化されたレート制限は未確認(EDINET_SOURCE_ONBOARDING.md §2)。
# 非公式情報(実運用上3〜5秒間隔が必要との言及)に基づく暫定的な安全マージン。
_RATE_LIMIT_INTERVAL_SEC = 5.0

_DOCUMENTS_LIST_SUCCESS_STATUS = "200"


class EdinetDownloadType(IntEnum):
    """Document Downloadの``type``パラメータ。

    **確度はメンバーごとに異なる(skeptic-reviewer Finding、D0046追記で明記)**:
    `MAIN_DOCUMENT_AND_AUDIT_REPORT`(1)のみ、ユーザーのローカル環境で実際に
    Downloadし、Content-Type(`application/octet-stream`)・ZIPマジックバイト・
    SHA-256を観測して確認済み(`OBSERVED`)。それ以外(2/3/4/5)は、ユーザーが
    ローカルで参照した公式仕様書の記述をそのまま反映したものであり、この
    Repository/Session自身では一度もDownloadを試みていない(`SPEC_CLAIM_ONLY`)。
    参照した仕様書の正確な版・URLはこのSession単独では特定できていない
    (`EDINET_SOURCE_ONBOARDING.md`が指摘した2024年7月版/2026年6月版のいずれか、
    または別版の可能性がある)。値を誤って取り違えていても、成功判定
    (`_SUCCESSFUL_DOWNLOAD_CONTENT_TYPES`によるContent-Type Allowlist)は
    それを検知できない(誤った`type`でも同じAllowlist内のContent-Typeが返れば
    成功と判定されてしまう)。値そのものを使う前に、各typeを一度は実際に
    Downloadして確認することを推奨する。
    """

    MAIN_DOCUMENT_AND_AUDIT_REPORT = 1  # 提出本文書及び監査報告書(ZIP)。OBSERVED(2026-08-17、docID=S100TD9S)。
    PDF = 2  # PDF。SPEC_CLAIM_ONLY(未Download確認)。
    ALTERNATIVE_ATTACHMENTS = 3  # 代替書面・添付文書(ZIP)。SPEC_CLAIM_ONLY(未Download確認)。
    ENGLISH_DOCUMENTS = 4  # 英文ファイル(ZIP)。SPEC_CLAIM_ONLY(未Download確認)。
    CSV = 5  # CSV(ZIP)。SPEC_CLAIM_ONLY(未Download確認)。


# type=2(PDF)のみapplication/pdf、それ以外(1/3/4/5、いずれもZIP)は
# application/octet-stream。ローカル実データで type=1 の application/octet-stream
# を確認済み。type=2/3/4/5 の実Content-Typeは未検証だが、公式仕様の記述
# (ZIP/PDF)からこの2値のいずれかになると判断する。
_SUCCESSFUL_DOWNLOAD_CONTENT_TYPES = frozenset({"application/octet-stream", "application/pdf"})
_ERROR_CONTENT_TYPE_PREFIX = "application/json"


class EdinetApiError(DataSourceError):
    """EDINET APIがHTTP 200かつ`metadata.status`がエラーを示す場合、または
    Document DownloadがエラーJSONを返した場合に送出する(`DataSourceError`の
    サブクラス、メッセージにAPIキーは含めない)。"""


def _safe_error_message(body: Any) -> str:
    """エラーレスポンスのJSON Bodyから、APIキーを含まない診断メッセージを組み立てる。

    EDINETのエラーBodyはServer側が生成するものであり、Client側のAPIキーが
    そのまま反射される既知の挙動は確認されていないが、念のため`metadata`
    以下の値のみを使い、Bodyの他の部分やRequest URLは含めない。
    """
    if not isinstance(body, dict):
        return "(レスポンスBodyが辞書形式ではありません)"
    metadata = body.get("metadata")
    if not isinstance(metadata, dict):
        return "(metadataフィールドが見つかりません)"
    status = metadata.get("status", "UNKNOWN")
    message = metadata.get("message", "(messageフィールドなし)")
    return f"metadata.status={status!r}, metadata.message={message!r}"


class EdinetAdapter:
    """EDINET API V2 への Raw HTTP Client(Phase4B-2、Local Real Data Validation済み)。

    Documents List(``/documents.json``)とDocument Download
    (``/documents/{docID}``)のRaw Fetchのみを提供する。Field-level
    Normalizationは`lib.disclosures.providers.edinet_normalize`が別途担う
    (このモジュール自体はNormalize/Entity解決を行わない)。
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
        (Snapshotへそのまま記録される側)には認証情報を一切含めない。

        `raise_for_status()`はTransport層(真のHTTP 4xx/5xx)のみを検知する。
        EDINET自身のアプリケーションレベルのエラー(HTTP 200 + metadata.status
        でのエラー表現)はここでは検知できないため、呼び出し元
        (`fetch_documents_list_raw`/`fetch_document_raw`)が個別に検証する。
        """
        api_key = self._require_configured()
        outgoing_params = dict(recorded_params)
        headers: dict[str, str] = {}
        if self._auth_style == "query_param":
            outgoing_params[_QUERY_PARAM_AUTH_KEY_NAME] = api_key
        else:
            headers[_HEADER_AUTH_KEY_NAME] = api_key

        self._throttle()
        failure_type_name: str | None = None
        resp: requests.Response | None = None
        try:
            resp = self._session.get(f"{BASE_URL}{endpoint}", params=outgoing_params, headers=headers, timeout=30)
            self._last_request_at = time.monotonic()
            resp.raise_for_status()
        except requests.RequestException as exc:
            failure_type_name = type(exc).__name__
        if failure_type_name is not None:
            # except節の外側でraiseするため、捕捉した例外オブジェクト(query_param
            # 認証方式の場合APIキーを含むURLを保持しうる)への参照は新しい例外の
            # __context__へ残らない。
            raise DataSourceError(f"{error_label}の取得に失敗しました({failure_type_name})")
        assert resp is not None
        return resp

    def fetch_documents_list_raw(self, target_date: date, *, list_type: int) -> RawFetchResult:
        """``GET /documents.json``: 指定日のDocuments Listを未加工のまま取得する。

        成功条件(すべて満たす場合のみ成功): (1) HTTP成功(Transport層)、
        (2) レスポンスBodyがJSONとして解釈できる、(3) ``metadata.status
        == "200"``、(4) ``results``キーがリストとして存在する。いずれかを
        満たさない場合は`EdinetApiError`を送出する(401/403/404/429/5xx相当の
        `metadata.status`はすべてこの経路でfail closedになる)。

        `date`/`type`という候補パラメータ名はローカル実データで実際に機能する
        ことを確認済み。1回の呼び出しにつき1日のみ(日付範囲・銘柄コードによる
        クエリが可能かは未確認、そのため本メソッドにcodes/date-range引数は
        持たせていない)。
        """
        recorded_params = {"date": target_date.isoformat(), "type": str(list_type)}
        resp = self._request("/documents.json", recorded_params, error_label="EDINET Documents List")
        try:
            body = resp.json()
        except ValueError as exc:
            raise DataSourceError("EDINET Documents Listのレスポンスが JSON として解釈できません") from exc

        if not isinstance(body, dict) or not isinstance(body.get("metadata"), dict):
            raise EdinetApiError("EDINET Documents Listのレスポンスに想定される'metadata'構造がありません")
        status = body["metadata"].get("status")
        if status != _DOCUMENTS_LIST_SUCCESS_STATUS:
            raise EdinetApiError(f"EDINET Documents Listが失敗を報告しました: {_safe_error_message(body)}")
        if not isinstance(body.get("results"), list):
            raise EdinetApiError("EDINET Documents Listのレスポンスに'results'リストがありません")

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
        """``GET /documents/{docID}``: 指定書類のダウンロード。

        成功条件(すべて満たす場合のみ成功): (1) HTTP成功(Transport層)、
        (2) Content-Typeが`_SUCCESSFUL_DOWNLOAD_CONTENT_TYPES`のいずれか
        (``application/octet-stream``または``application/pdf``)。
        Content-Typeが``application/json``系の場合はエラーBody(EDINET側の
        既知の挙動、ローカル実データで確認済み)とみなし`EdinetApiError`を
        送出する。それ以外の未知Content-Typeもfail closedで拒否する
        (「成功として知られている型のみ許可」というAllowlist方式)。

        `download_type`(`type`パラメータ)は`EdinetDownloadType`で公式仕様 +
        ローカル実データ(type=1)により意味が確認されているが、値そのものは
        呼び出し側が明示的に指定する(既定値は持たせない)。

        レスポンスは通常バイナリ(ZIP/PDF)のため、`RawFetchResult.payload`は
        `lib.snapshot.RawSnapshotStore`(JSON保存)と互換になるよう
        ``{"content_base64": ..., "content_type": ..., "content_sha256": ...}``
        の形でBase64エンコードして保持する(base64は可逆でありByte-for-Byteの
        整合性を保つ。`content_sha256`は元のバイト列(Base64化前)に対して
        計算したCanonical Hash。Content自体の解析・展開は一切行わない)。
        """
        recorded_params = {"type": str(download_type)}
        resp = self._request(f"/documents/{source_document_id}", recorded_params, error_label="EDINET Document Download")

        content_type = resp.headers.get("Content-Type", "")
        content_type_base = content_type.split(";")[0].strip()
        if content_type_base.startswith(_ERROR_CONTENT_TYPE_PREFIX):
            try:
                error_body = resp.json()
            except ValueError:
                error_body = None
            raise EdinetApiError(f"EDINET Document Downloadが失敗を報告しました: {_safe_error_message(error_body)}")
        if content_type_base not in _SUCCESSFUL_DOWNLOAD_CONTENT_TYPES:
            raise EdinetApiError(f"EDINET Document Downloadの Content-Type が想定外です(observed={content_type_base!r})")

        raw_bytes = resp.content
        payload = {
            "content_base64": base64.b64encode(raw_bytes).decode("ascii"),
            "content_type": content_type,
            "content_sha256": hashlib.sha256(raw_bytes).hexdigest(),
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


__all__ = [
    "EdinetAdapter",
    "EdinetApiError",
    "EdinetDownloadType",
    "BASE_URL",
    "RESPONSE_SCHEMA_VERSION",
]
