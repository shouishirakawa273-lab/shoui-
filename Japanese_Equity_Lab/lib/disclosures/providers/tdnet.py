"""J-Quants API V2 TDnet/適時開示情報アドオンへの接続(Phase4B-3、D0048)。

**Provenance(最重要、必ず読むこと)**: このModuleが前提とするEndpoint名・
Field名・挙動は、本Repository/Session自身が`jpx-jquants.com`等へ接続して
確認したものでは**ない**。ユーザーが、別のWeb-access環境(本セッションとは
異なる、Egress制限の無い環境)から2026-08-17時点の公式ページを直接確認した
として、その結果をこのSessionへ報告した内容(`TDNET_SOURCE_ONBOARDING.md`
「EXTERNAL_OFFICIAL_SPEC_VERIFICATION」セクション参照)を実装の根拠として
使用している。

- Provenance Tag: `EXTERNAL_OFFICIAL_SPEC_VERIFICATION`
  (`USER_SUPPLIED_OFFICIAL_VERIFICATION`と同義として扱う)。
- Claude自身がこのSession内で一次資料を直接Fetchして確認したものではない。
- 真の意味でのLocal Real Data Validation(実際にAdd-on契約済みのAPI Keyで
  `/v2/td/list`等を呼び出し、Response実物を観測すること)は、まだ行われて
  いない。それが完了するまでPhase4B-3全体は`CODE_COMPLETE_AWAITING_
  ADDON_LOCAL_VALIDATION`のままとする(`DECISIONS.md` D0048参照)。

**BASE_URLについての推論(明示)**: ユーザー申告は`GET /v2/td/list`等の
Path形式のみを述べており、完全なHost名までは明示していない。TDnet
Add-onは「J-Quants API」(個人向け、既存`lib.data_sources.jquants.
JQuantsAdapter`と同一製品)の機能として確認されたため、既存の確認済み
Host(`https://api.jquants.com/v2`、D0039)を共有すると推論している。
この推論自体はEXTERNAL_OFFICIAL_SPEC_VERIFICATIONの直接申告ではなく、
Main Claudeによる妥当な補完である(Local Real Data Validationで確認が
必要な項目として`TDNET_LOCAL_VALIDATION_GUIDE.md`にも明記する)。

## 確認済み(ユーザー申告)の重要な挙動上の区別

`DiscStatus`/`RevNo`について、**Provider宣言Schema意味論**(仕様として
定義されている値の範囲: `DiscStatus`はnull/revision/delete、`RevNo`は
1〜99)と、**現在の実装挙動**(`DiscStatus`は現在常にnull、`RevNo`は現在
常に1)は別軸として扱う。Normalizer(`tdnet_normalize.py`)はこの2軸を
混同しない。現在の実装挙動を「訂正が無い」ことの確認的Signalとして
解釈しない(将来Providerの実装が変わり、これらのFieldが実際に意味を
持ち始める可能性があるため)。

開示File自体が訂正された場合は新しい`DiscNo`が発行され、独立した新規
Recordとして扱われる(ユーザー申告)。**このAdapter/Normalizerは、新しい
`DiscNo`が過去の`DiscNo`を訂正した、という明示的な関係性Recordを一切
自動生成しない**(タスク上最重要の禁止事項、`lib.disclosures.model`の
既存原則「時系列だけからの推測は禁止する」をそのまま踏襲。関係性Record
自体の型名は`lib.disclosures.model`参照、この禁止事項を説明する際に
このModule自身では言及しない — 構造的Test`test_tdnet_adapter_never_
constructs_document_relationship`が型名の非出現そのものを確認するため)。

## Cursor / Pagination

`cursor`(当日Real-time差分取得用)と`pagination_key`(既存`JQuantsAdapter.
_get_all_pages`と同じPagination意味論)は同時指定不可(ユーザー申告)。
このAdapterは呼び出し時点でこの制約を検証し、両方が指定された場合は
`ValueError`をfail closedで送出する。`cursor`はいかなるTimestampとしても
解釈しない(`lib.disclosures.providers.tdnet_cursor.
TdnetRetrievalCursorState`の既存設計と整合)。

## Ephemeral URL Safety

`/v2/td/files`・`/v2/td/bulk`のDownload URLは15分で失効する(ユーザー
申告)。このAdapterはURLをそのままRaw Payloadの一部として返す(Metadata
取得のみが責務であり、File本体のDownloadはこのPhaseでは行わない)が、
呼び出し側は`raw_snapshot_ref`等の安定した識別子でProvenanceを構築し、
URL自体を恒久的な参照先として保存してはならない
(`TDNET_ARCHITECTURE.md` §5参照)。

## レート制限

TDnet/Company Disclosure Add-on APIは100リクエスト/分、通常Plan Rate
Limit(D0039確認済みの60/分)とは独立(ユーザー申告)。このAdapterは
`JQuantsAdapter`とは別のThrottle State(インスタンスごとに独立した
`_last_request_at`)を持ち、Plan全体のThrottleとは別に自身の呼び出し
間隔を制御する。429を受け取った場合は`Retry-After`Headerを尊重して
Back offし、既定の最大Retry回数を超えた場合のみ`DataSourceError`を
送出する。
"""

from __future__ import annotations

import logging
import os
import time
from datetime import UTC, date, datetime
from typing import Any

import requests

from lib.data_sources.base import RawFetchResult
from lib.errors import DataSourceError

logger = logging.getLogger(__name__)

BASE_URL = "https://api.jquants.com/v2"
RESPONSE_SCHEMA_VERSION = (
    "tdnet-v2(EXTERNAL_OFFICIAL_SPEC_VERIFICATION: ユーザーが別のWeb-access環境から"
    "2026-08-17時点のjpx-jquants.com/www.jpx.co.jpを直接確認したと申告した内容に基づく。"
    "Claude自身がこのSession内で一次資料をFetchして確認したものではない。真のLocal Real "
    "Data Validationは未実施 — Japanese_Equity_Lab/TDNET_SOURCE_ONBOARDING.md "
    "'EXTERNAL_OFFICIAL_SPEC_VERIFICATION'セクション参照)"
)

# TDnet/Company Disclosure Add-on APIは100リクエスト/分(ユーザー申告、通常Plan
# Rate Limitとは独立)。60秒/100回=0.6秒に安全マージンを付与(jquants.pyの
# 60req/分に対する1.05秒[+5%]と同じ考え方)。
_RATE_LIMIT_INTERVAL_SEC = 0.63
_MAX_429_RETRIES = 3
_DEFAULT_429_BACKOFF_SEC = 5.0


class TdnetApiError(DataSourceError):
    """TDnet Add-on APIがエラーを報告した場合に送出する(`DataSourceError`のサブクラス)。

    EDINET(D0046)で確認されたような「HTTP 200でApplication Errorを隠す」
    パターンがTDnet Add-onにも存在するかどうかは確認も反証もされていない
    (`TDNET_SOURCE_ONBOARDING.md`未言及)。このAdapterは確認されていない
    Error Envelope形状を推測でコード化せず、Transport層(`raise_for_status()`)
    のみに依拠する。将来Local Real Data Validationでこのパターンが観測された
    場合は、EDINETと同様の明示的Application-level成功条件チェックを追加すること。
    """


def _parse_retry_after(header_value: str | None) -> float:
    if header_value is None:
        return _DEFAULT_429_BACKOFF_SEC
    try:
        parsed = float(header_value)
    except ValueError:
        return _DEFAULT_429_BACKOFF_SEC
    return max(parsed, 0.0)


class TdnetAdapter:
    """TDnet/Company Disclosure Timely Disclosure Add-on(J-Quants API V2)への Raw HTTP Client。

    `/v2/td/list`(Documents List)・`/v2/td/files`(File Metadata)・
    `/v2/td/bulk`(Bulk Metadata)のRaw Fetchのみを提供する。Field-level
    Normalizationは`lib.disclosures.providers.tdnet_normalize`が別途担う
    (このModule自体はNormalize/Entity解決/Event解釈を行わない)。

    実際のFile本体(PDF/XBRL/CSV bytes)のDownloadはこのPhaseでは実装しない
    (`/v2/td/files`/`/v2/td/bulk`が返すのはMetadata[URLを含む]のみ)。
    """

    def __init__(self, api_key: str | None = None, session: requests.Session | None = None) -> None:
        self._api_key = api_key or os.environ.get("JQUANTS_API_KEY")
        self._session = session or requests.Session()
        self._last_request_at: float = 0.0

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def _require_configured(self) -> str:
        if not self._api_key:
            raise DataSourceError(
                "JQUANTS_API_KEY が設定されていません(.envを確認してください、TDnet Add-onも同じKeyを使用します)"
            )
        return self._api_key

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < _RATE_LIMIT_INTERVAL_SEC:
            time.sleep(_RATE_LIMIT_INTERVAL_SEC - elapsed)

    def _request(self, endpoint: str, params: dict[str, str], *, error_label: str) -> requests.Response:
        """`except`節の外側でraiseすることで、捕捉した例外オブジェクトへの参照が
        新しい例外の`__context__`へ残らないようにする(EDINET Adapterの既存
        `_request`と同じ設計、認証情報を含みうる例外の再露出を避ける)。
        """
        api_key = self._require_configured()
        for attempt in range(_MAX_429_RETRIES + 1):
            self._throttle()
            failure_type_name: str | None = None
            resp: requests.Response | None = None
            try:
                resp = self._session.get(f"{BASE_URL}{endpoint}", params=params, headers={"x-api-key": api_key}, timeout=30)
            except requests.RequestException as exc:
                failure_type_name = type(exc).__name__
            if failure_type_name is not None:
                raise DataSourceError(f"{error_label}の取得に失敗しました({failure_type_name})")
            assert resp is not None
            self._last_request_at = time.monotonic()

            if resp.status_code == 429:
                if attempt >= _MAX_429_RETRIES:
                    raise TdnetApiError(
                        f"{error_label}がRate Limit(429)により失敗しました(リトライ上限{_MAX_429_RETRIES}回に到達)"
                    )
                backoff_sec = _parse_retry_after(resp.headers.get("Retry-After"))
                logger.warning(
                    "tdnet: 429 Too Many Requestsを受信しました。%s秒待機してリトライします(%d/%d)",
                    backoff_sec,
                    attempt + 1,
                    _MAX_429_RETRIES,
                )
                time.sleep(backoff_sec)
                continue

            http_error_status: int | None = None
            try:
                resp.raise_for_status()
            except requests.HTTPError:
                http_error_status = resp.status_code
            if http_error_status is not None:
                raise DataSourceError(f"{error_label}の取得に失敗しました(HTTP {http_error_status})")
            return resp
        raise AssertionError("unreachable: リトライループが正常終了しませんでした")

    def fetch_documents_list_raw(
        self,
        *,
        target_date: date | None = None,
        code: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        cursor: str | None = None,
        pagination_key: str | None = None,
        disc_items: str | None = None,
    ) -> RawFetchResult:
        """``GET /v2/td/list``: 開示Documents Listを未加工のまま取得する。

        ``target_date``/``code``はどちらか一方が必須(ユーザー申告の
        「``date``または``code``必須」を、両方同時指定時の未確認挙動を
        避けるためXOR[排他的選択]として実装)。``from_date``/``to_date``
        (期間クエリ)は``code``指定時のみ有効(``target_date``との組み合わせは
        未確認のためfail closed)。``cursor``/``pagination_key``は同時
        指定不可(ユーザー申告、公式仕様)。

        ``disc_items``はOpaqueなRaw Query Parameterとしてのみ扱う(公式Code
        Listが未確認のため、このAdapterはその意味論を一切解釈しない)。
        """
        if cursor is not None and pagination_key is not None:
            raise ValueError("cursorとpagination_keyは同時指定できません(EXTERNAL_OFFICIAL_SPEC_VERIFICATION)")
        if (target_date is None) == (code is None):
            raise ValueError("target_dateまたはcodeのいずれか一方が必須です(EXTERNAL_OFFICIAL_SPEC_VERIFICATION)")
        if target_date is not None and (from_date is not None or to_date is not None):
            raise ValueError(
                "target_date指定時にfrom_date/to_dateを組み合わせる挙動は未確認のため許可しません(code指定時のみ使用できます)"
            )

        params: dict[str, str] = {}
        if target_date is not None:
            params["date"] = target_date.isoformat()
        if code is not None:
            params["code"] = code
        if from_date is not None:
            params["from"] = from_date.isoformat()
        if to_date is not None:
            params["to"] = to_date.isoformat()
        if cursor is not None:
            params["cursor"] = cursor
        if pagination_key is not None:
            params["pagination_key"] = pagination_key
        if disc_items is not None:
            params["discItems"] = disc_items

        resp = self._request("/td/list", params, error_label="TDnet Documents List")
        try:
            body: Any = resp.json()
        except ValueError as exc:
            raise DataSourceError("TDnet Documents Listのレスポンスが JSON として解釈できません") from exc
        if not isinstance(body, dict):
            raise TdnetApiError("TDnet Documents Listのレスポンスが想定される辞書構造ではありません")

        if target_date is not None:
            data_period = target_date.isoformat()
        elif from_date is not None or to_date is not None:
            data_period = f"code={code}:{(from_date.isoformat() if from_date else '')}/{(to_date.isoformat() if to_date else '')}"
        else:
            data_period = f"code={code}:past_5_years(coverage_window_semantics_unconfirmed)"

        return RawFetchResult(
            source="TDNET",
            endpoint="/v2/td/list",
            request_parameters=params,
            retrieved_at=datetime.now(UTC),
            data_period=data_period,
            response_schema_version=RESPONSE_SCHEMA_VERSION,
            payload=body,
        )

    def fetch_files_raw(self, disc_no: str, *, docs: str | None = None) -> RawFetchResult:
        """``GET /v2/td/files``: 指定開示のFile Metadata(Ephemeral Download URL含む)を取得する。

        ``docs``(``g``=Full PDF/``s``=Summary PDF/``x``=XBRL、ユーザー申告)は
        任意。File本体のDownloadはこのPhaseでは行わない(Metadata取得のみ)。
        Responseに含まれるDownload URLは15分で失効する(ユーザー申告) —
        呼び出し側はこのURLを恒久的なLocatorとして保存してはならない。
        """
        params: dict[str, str] = {"discNo": disc_no}
        if docs is not None:
            params["docs"] = docs

        resp = self._request("/td/files", params, error_label="TDnet Files")
        try:
            body: Any = resp.json()
        except ValueError as exc:
            raise DataSourceError("TDnet Filesのレスポンスが JSON として解釈できません") from exc
        if not isinstance(body, dict):
            raise TdnetApiError("TDnet Filesのレスポンスが想定される辞書構造ではありません")

        return RawFetchResult(
            source="TDNET",
            endpoint="/v2/td/files",
            request_parameters=params,
            retrieved_at=datetime.now(UTC),
            data_period=disc_no,
            response_schema_version=RESPONSE_SCHEMA_VERSION,
            payload=body,
        )

    def fetch_bulk_raw(self) -> RawFetchResult:
        """``GET /v2/td/bulk``: Bulk CSV(gzip圧縮、過去5年)のMetadata(``lastUpdated``/``url``)を取得する。

        CSV本体のDownloadはこのPhaseでは行わない(Metadata取得のみ)。
        ``url``は15分で失効する(ユーザー申告) — 恒久的なLocatorとして
        保存してはならない。``lastUpdated``はDisclosure Timeではない
        (ユーザー明示の指示、PIT Fieldとして使わないこと)。
        """
        resp = self._request("/td/bulk", {}, error_label="TDnet Bulk")
        try:
            body: Any = resp.json()
        except ValueError as exc:
            raise DataSourceError("TDnet Bulkのレスポンスが JSON として解釈できません") from exc
        if not isinstance(body, dict):
            raise TdnetApiError("TDnet Bulkのレスポンスが想定される辞書構造ではありません")

        return RawFetchResult(
            source="TDNET",
            endpoint="/v2/td/bulk",
            request_parameters={},
            retrieved_at=datetime.now(UTC),
            data_period="bulk(past_5_years)",
            response_schema_version=RESPONSE_SCHEMA_VERSION,
            payload=body,
        )


__all__ = [
    "BASE_URL",
    "RESPONSE_SCHEMA_VERSION",
    "TdnetAdapter",
    "TdnetApiError",
]
