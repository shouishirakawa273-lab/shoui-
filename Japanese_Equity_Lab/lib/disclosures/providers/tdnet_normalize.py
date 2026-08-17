"""TDnet(`/v2/td/list`)Raw Payload -> `DisclosureDocument` + TDnet固有Metadata(Phase4B-3、D0048)。

**Provenance(最重要)**: このModuleが前提とするField名・意味論は、Claude自身が
このSession内で一次資料をFetchして確認したものでは**ない**。ユーザーが別の
Web-access環境から2026-08-17時点の公式ページを直接確認したと申告した内容
(`TDNET_SOURCE_ONBOARDING.md`「EXTERNAL_OFFICIAL_SPEC_VERIFICATION」セクション
参照)を実装の根拠として使用している(Provenance Tag: `EXTERNAL_OFFICIAL_
SPEC_VERIFICATION`)。真の意味でのLocal Real Data Validationはまだ行われて
いない。

## Envelope形状についての推論(明示)

ユーザー申告はField名の列挙(`DiscNo`/`Code`/.../`cursor`/`pagination_key`)
であり、実際のJSON構造例までは示していない。このModuleは既存
`JQuantsAdapter._get_all_pages`が前提とする`{"data": [...], "pagination_key":
...}`という既存製品の共通Envelope規約を踏襲し、`{"data": [...], "cursor":
..., "pagination_key": ...}`という形状を推論している。この推論はMain Claude
による妥当な補完であり、EXTERNAL_OFFICIAL_SPEC_VERIFICATIONの直接申告では
ない(`TDNET_LOCAL_VALIDATION_GUIDE.md`で確認対象として明記する)。

## Provider宣言Schema vs 現在の実装挙動(最重要、`TDNET_ARCHITECTURE.md` §2)

`DiscStatus`/`RevNo`について、ユーザー申告は以下の2つを明確に分離している:

- **Provider宣言Schema意味論**: `DiscStatus`はnull(=新規)/`"revision"`
  (=訂正)/`"delete"`(=削除)のいずれかを表しうる。`RevNo`は1〜99を取りうる。
- **現在の実装挙動**: `DiscStatus`は現在常にnull。`RevNo`は現在常に1。
  Title訂正はReturnされるAPI Dataに反映されない。削除された開示も返り
  続ける。開示File自体が訂正された場合は新しい`DiscNo`が発行され、独立した
  新規Recordとして扱われる。

このModuleは`DiscStatus`をSchema宣言通りにParseする(`TdnetDiscStatus`)が、
**その結果を「この文書は訂正/削除されていない」ことの確認的Signalとして
一切使わない**。現在の実装挙動(常にnull)は、将来Providerの実装が変わる
可能性がある「観測された挙動」であって、「Schemaがそうあり続ける保証」では
ない(`TDNET_ARCHITECTURE.md` §2)。

## 最重要の禁止事項: 訂正Relationshipの自動生成禁止

新しい`DiscNo`が過去の`DiscNo`を訂正した、という明示的な関係性Recordを
このModuleは一切生成しない(タスク上最重要の禁止事項)。関係性Record自体の
型名は`lib.disclosures.model`参照、この禁止事項を説明する際にこのModule
自身では言及しない(構造的Test`test_tdnet_normalize_never_constructs_
document_relationship`が型名の非出現そのものを確認するため)。

## `market_public_at`(PIT上最重要、EXTERNAL_OFFICIAL_SPEC_VERIFICATION §7)

ユーザー申告: TDnet経由で情報が開示された時、同じ会社情報がTDnetの開示Time
に適時開示情報閲覧サービス上で同時に公衆縦覧可能になる。したがって`DiscDate`
+ `DiscTime`(Asia/Tokyo)から`market_public_at`の値そのものは構築する。

**ただし`market_public_at_basis`は`AvailabilityBasis.EXACT`ではなく
`AvailabilityBasis.UNKNOWN`とする(skeptic-reviewer Finding、D0048追記で
修正)。** 理由: この確認根拠(EXTERNAL_OFFICIAL_SPEC_VERIFICATION)は
Claude自身がこのSession内で一次資料をFetchして確認したものではなく、
ユーザーが別のWeb-access環境から確認したと申告した内容の又聞きに過ぎない。
EDINETは実際に`api.edinet-fsa.go.jp`へHTTP疎通し`submitDateTime`Fieldの
実在自体は確認済み(D0046、CONNECTEDまで昇格)という、これより強い証拠を
持ちながらも、「`submitDateTime`が真にMarket Public Timeと一致するか」
という意味論的な結びつき自体は未確認だったため`market_public_at`を
`None`/`UNKNOWN`のまま維持した(`edinet_normalize.py`参照)。TDnetの
`DiscDate`+`DiscTime`→`market_public_at`という意味論的結びつきの確認
根拠は、EDINETのそれよりもさらに弱い(一次資料への直接Fetch自体が一度も
行われていない)。したがって、値は構築しつつ`AvailabilityBasis.UNKNOWN`
とすることで、`lib.disclosures.view.disclosures_as_of()`の既定の安全側
除外(UNKNOWN Basisの文書は`include_unknown_availability=True`を明示しない
限り除外される、既存の確認済み安全機構、D0045/D0046)がTDnetにもそのまま
適用されるようにする。真のLocal Real Data Validationでこのmapping自体が
確認された時点で、`AvailabilityBasis.EXACT`への昇格を検討すること。

`provider_available_at`はこのMappingでは確定できず、実際の観測ログが
無い限り`AvailabilityBasis.UNKNOWN`のまま(Fallbackしない、
`lib.fundamentals.normalize._provider_available_at_and_basis`と同じ保守的
方針)。

## `document_kind`のMapping — 意図的に行わない

`DiscItems`の公式Code List(商品分類+会社分類+開示項目の桁構成)は未確認
(`TDNET_SOURCE_ONBOARDING.md` §9)。したがって`document_kind`は常に
`DocumentKind.UNKNOWN`のままとし、`DiscItems`/`Docs`はOpaqueなRaw値として
`TdnetDocumentMetadata`へ保持するのみで、意味論を一切解釈しない。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from zoneinfo import ZoneInfo

from lib.data_sources.ticker_codes import TickerCodeNormalizationError, normalize_provider_code_to_internal
from lib.disclosures.model import NORMALIZER_VERSION, DisclosureDocument, DocumentKind
from lib.errors import DataSourceError
from lib.evidence.model import AvailabilityBasis

logger = logging.getLogger(__name__)

_JST = ZoneInfo("Asia/Tokyo")

TDNET_NORMALIZER_VERSION = f"{NORMALIZER_VERSION}+TDNET_V1"

# Schema Evolution追跡用(`TDNET_ARCHITECTURE.md` §2の設計をそのまま実装)。
# 「2026-08-17時点でこのProvider宣言Schema/観測された実装挙動をこのように理解した」
# という記録であり、Providerの実装が将来変わっても過去の正規化済みRecordを
# Silentに遡及的再解釈しないためのVersion Marker。
TDNET_PROVIDER_SCHEMA_VERSION = "EXTERNAL_OFFICIAL_SPEC_VERIFICATION_2026-08-17"
TDNET_OBSERVED_BEHAVIOR_DOCUMENTED_AT = date(2026, 8, 17)


class TdnetDiscStatus(StrEnum):
    """`DiscStatus`(Provider宣言Schema意味論、EXTERNAL_OFFICIAL_SPEC_VERIFICATION)。

    **現在の実装挙動(ユーザー申告)は常にnull(=`NEW`)である。** この値を
    「この文書はまだ訂正/削除されていない」ことの確認的Evidenceとして使って
    はならない — 現在の実装挙動が将来変わる可能性があり、その場合でも過去に
    正規化済みのRecordを遡及的に再解釈しない(`TDNET_ARCHITECTURE.md` §2)。
    """

    NEW = "NEW"  # null(Schema宣言値)。現在の実装挙動として常にこの値。
    REVISION = "REVISION"  # "revision"
    DELETE = "DELETE"  # "delete"
    UNKNOWN = "UNKNOWN"  # Schema宣言に無い未知の非null値(fail closed)


_DISC_STATUS_MAP: dict[str, TdnetDiscStatus] = {
    "revision": TdnetDiscStatus.REVISION,
    "delete": TdnetDiscStatus.DELETE,
}


def _parse_disc_status(raw: object) -> TdnetDiscStatus:
    """`raw`が`None`(Key欠損 or 明示的null、いずれもSchema宣言上は同じ「新規」を
    意味する)の場合は`NEW`を返す。非null値でSchema宣言に無いものは`UNKNOWN`へ
    fail closedし、警告を残す(未知値をSilentに無視・0扱いしない、既存
    `_parse_lifecycle_value`パターンと同じ設計)。"""
    if raw is None:
        return TdnetDiscStatus.NEW
    raw_str = str(raw).strip()
    status = _DISC_STATUS_MAP.get(raw_str)
    if status is None:
        logger.warning("tdnet: 未知のDiscStatus値 '%s' を検出しました。UNKNOWNへfail closedします", raw_str)
        return TdnetDiscStatus.UNKNOWN
    return status


def _parse_rev_no(raw: object) -> int | None:
    """`RevNo`(Schema宣言は1〜99、現在の実装挙動は常に1、ユーザー申告)。
    この値をRevision回数のEvidenceとして解釈せず、単なるRaw値として保持する。
    """
    if raw is None:
        return None
    try:
        return int(str(raw))
    except (TypeError, ValueError):
        logger.warning("tdnet: RevNo値 %r をintへParseできません", raw)
        return None


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _opaque_raw(value: object) -> str | None:
    """`DiscItems`/`Docs`のような、意味論を解釈しないRaw値をそのまま保持する。

    公式Code List(`DiscItems`)・短縮Codeの完全な意味論(`Docs`)がいずれも
    未確認のため、このModuleは値の構造(list/dict/str)を一切解釈しない。
    文字列以外(list/dict等)はJSON文字列化してそのまま保持する(情報の欠落を
    避けるため)。
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _parse_date_or_none(raw: object) -> date | None:
    if raw is None:
        return None
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        logger.warning("tdnet: 不正なDiscDate値 '%s' を検出しました", raw)
        return None


def _build_market_public_at(disc_date_raw: object, disc_time_raw: object) -> tuple[datetime | None, AvailabilityBasis]:
    """`DiscDate`+`DiscTime`から`market_public_at`の値を構築する(EXTERNAL_
    OFFICIAL_SPEC_VERIFICATION §7で申告されたMapping)。`lib.fundamentals.
    normalize._build_market_public_at`と同じ設計(DiscTimeが無い/不明な場合、
    15:00等を推測で補完しない)。

    **Basisは値が構築できた場合でも常に`AvailabilityBasis.UNKNOWN`を返す**
    (`AvailabilityBasis.EXACT`は使わない、モジュールDocstring「market_
    public_at」節参照)。確認根拠が又聞き[EXTERNAL_OFFICIAL_SPEC_
    VERIFICATION]であり、Claude自身の直接確認・真のLocal Real Data
    Validationのいずれでもないため、`disclosures_as_of()`の既定安全側
    除外(UNKNOWN Basisは`include_unknown_availability=True`を明示しない
    限り除外)がそのまま適用されるようにする。
    """
    if disc_date_raw is None or disc_time_raw is None:
        return None, AvailabilityBasis.UNKNOWN
    try:
        d = date.fromisoformat(str(disc_date_raw))
        time_parts = str(disc_time_raw).split(":")
        hour, minute = int(time_parts[0]), int(time_parts[1])
        dt = datetime(d.year, d.month, d.day, hour, minute, tzinfo=_JST)
    except (ValueError, IndexError):
        logger.warning("tdnet: DiscDate/DiscTime ('%s'/'%s') からmarket_public_atを構築できません", disc_date_raw, disc_time_raw)
        return None, AvailabilityBasis.UNKNOWN
    return dt, AvailabilityBasis.UNKNOWN


def _parse_entity_id(provider_code: str | None) -> str | None:
    """`Code`(4桁+末尾ゼロパディングの5桁化、EXTERNAL_OFFICIAL_SPEC_VERIFICATION
    §3で既存D0036パターンと一致すると確認済み)を内部Codeへ正規化する。正規化
    できない場合(優先株等の可能性)は推測せず`None`へfail closedする。

    **pit-auditor Finding対応**: `normalize_provider_code_to_internal()`は
    数字以外の文字列(合成Fixture用のRaw Labelを想定した既存の設計、
    `lib.data_sources.ticker_codes`Docstring参照)をそのまま変更せず返す
    ため、この関数へ数字以外の値をそのまま渡すと`entity_id`が非4桁の
    Raw文字列のまま設定されてしまう(Fail Closedの主張と矛盾する)。TDnetの
    `Code`Fieldが数字のみであることは未確認(`TDNET_SOURCE_ONBOARDING.md`
    参照)のため、ここで明示的に数字のみであることを確認してから委譲する。
    """
    if provider_code is None:
        return None
    if not provider_code.isdigit():
        logger.warning("tdnet: provider_code=%s が数字のみではないため、Noneへfail closedします", provider_code)
        return None
    try:
        return normalize_provider_code_to_internal(provider_code)
    except TickerCodeNormalizationError:
        logger.warning("tdnet: provider_code=%s を内部Codeへ正規化できません(普通株以外の可能性)", provider_code)
        return None


@dataclass(kw_only=True, frozen=True)
class TdnetDocumentMetadata:
    """TDnet固有の確認済みField(Provider-neutral Common Coreへは含めない)。

    `document_internal_id`が対応する`DisclosureDocument.internal_document_id`
    への参照キー。
    """

    document_internal_id: str
    disc_no: str | None = None
    provider_code: str | None = None
    name: str | None = None
    disc_date: date | None = None
    disc_time_raw: str | None = None
    disc_status: TdnetDiscStatus = TdnetDiscStatus.NEW
    rev_no: int | None = None
    disc_items_raw: str | None = None
    docs_raw: str | None = None
    provider_schema_version: str = TDNET_PROVIDER_SCHEMA_VERSION
    observed_behavior_documented_at: date = TDNET_OBSERVED_BEHAVIOR_DOCUMENTED_AT


def _parse_row(
    row: Mapping[str, object], *, index: int, retrieved_at: datetime, raw_snapshot_ref: str | None
) -> tuple[DisclosureDocument, TdnetDocumentMetadata]:
    """**pit-auditor Finding(D0048追記)**: `internal_document_id`は
    `index`(この1回の`/v2/td/list`呼び出しのPayload内での位置)を含む
    (EDINETの既存Pattern、`edinet_normalize.py`と同じ設計)。TDnetは
    `cursor`による当日差分Pollingを想定しており、同じ`disc_no`が別々の
    Retrieval呼び出しで異なる`index`を持って出現しうる(例: Cursor Window
    が重複した場合)。この場合`internal_document_id`は呼び出しごとに
    異なる値になるため、同一Disclosureの重複検知には`internal_document_id`
    ではなく`source_document_id`(=`disc_no`)を使うこと(`lib.disclosures.
    normalize.find_same_source_document_id_signals()`、既存D0045機構)。
    将来Cursorベースの継続的Ingestion Pipelineを構築する際は、この
    重複検知を必須Stepとして組み込むこと。
    """
    disc_no = _optional_str(row.get("DiscNo"))
    internal_document_id = f"TDNET_{disc_no or 'UNKNOWN'}_{index}"
    title = _optional_str(row.get("Title")) or f"[TDnet DiscNo={disc_no or 'UNKNOWN'}: Title unavailable]"
    provider_code = _optional_str(row.get("Code"))
    disc_date_raw = row.get("DiscDate")
    disc_time_raw = _optional_str(row.get("DiscTime"))
    market_public_at, market_public_at_basis = _build_market_public_at(disc_date_raw, disc_time_raw)
    rev_no = _parse_rev_no(row.get("RevNo"))

    document = DisclosureDocument(
        internal_document_id=internal_document_id,
        source_document_id=disc_no,
        entity_id=_parse_entity_id(provider_code),
        title=title,
        document_kind=DocumentKind.UNKNOWN,
        originating_source="TDnet",
        delivery_provider="J-Quants",
        market_public_at=market_public_at,
        market_public_at_basis=market_public_at_basis,
        provider_available_at=None,
        provider_available_at_basis=AvailabilityBasis.UNKNOWN,
        retrieved_at=retrieved_at,
        source_version=(str(rev_no) if rev_no is not None else None),
        raw_snapshot_ref=raw_snapshot_ref,
        language=None,
        attachments=(),
        normalizer_version=TDNET_NORMALIZER_VERSION,
    )

    doc_metadata = TdnetDocumentMetadata(
        document_internal_id=internal_document_id,
        disc_no=disc_no,
        provider_code=provider_code,
        name=_optional_str(row.get("Name")),
        disc_date=_parse_date_or_none(disc_date_raw),
        disc_time_raw=disc_time_raw,
        disc_status=_parse_disc_status(row.get("DiscStatus")),
        rev_no=rev_no,
        disc_items_raw=_opaque_raw(row.get("DiscItems")),
        docs_raw=_opaque_raw(row.get("Docs")),
    )
    return document, doc_metadata


def parse_tdnet_documents_list_payload(
    body: Mapping[str, object],
    *,
    retrieved_at: datetime,
    raw_snapshot_ref: str | None = None,
) -> list[tuple[DisclosureDocument, TdnetDocumentMetadata]]:
    """TDnet Documents List(``GET /v2/td/list``)の生Payload(既に`TdnetAdapter.
    fetch_documents_list_raw`が成功と判定したもの、または保存済みRaw Snapshotから
    読み込んだもの)を`DisclosureDocument`と`TdnetDocumentMetadata`のペアの列へ
    変換する。

    Envelope形状(`{"data": [...], ...}`)はMain Claudeによる推論であり、
    ユーザーのEXTERNAL_OFFICIAL_SPEC_VERIFICATION申告そのものではない
    (モジュールDocstring参照)。`data`キーが無い/リストでない場合は
    `DataSourceError`を送出する。行単位のParse失敗は個別行をスキップせず、
    Fieldごとにfail closed値(None/UNKNOWN)を設定した上でDocument自体は
    生成する(EDINET Phase4B-2と同じ方針、1行の不整合で全体のParseを止めない)。
    """
    data = body.get("data")
    if not isinstance(data, Sequence) or isinstance(data, (str, bytes)):
        raise DataSourceError("TDnet Documents List payloadに'data'リストがありません(推論した Envelope形状と一致しません)")

    parsed: list[tuple[DisclosureDocument, TdnetDocumentMetadata]] = []
    for index, row in enumerate(data):
        if not isinstance(row, Mapping):
            logger.warning("tdnet: data[%d] が辞書形式ではありません。スキップします", index)
            continue
        parsed.append(_parse_row(row, index=index, retrieved_at=retrieved_at, raw_snapshot_ref=raw_snapshot_ref))
    return parsed


def extract_retrieval_cursor_fields(body: Mapping[str, object]) -> tuple[str | None, str | None]:
    """Payloadから`cursor`/`pagination_key`を、意味論を一切解釈せずそのまま
    取り出す(呼び出し側が`lib.disclosures.providers.tdnet_cursor.
    TdnetRetrievalCursorState`を構築する材料としてのみ使う。このModule自体は
    Cursor Stateを構築しない、`DisclosureDocument`とは完全に分離したまま)。
    """
    cursor = body.get("cursor")
    pagination_key = body.get("pagination_key")
    return (_optional_str(cursor), _optional_str(pagination_key))


__all__ = [
    "TDNET_NORMALIZER_VERSION",
    "TDNET_OBSERVED_BEHAVIOR_DOCUMENTED_AT",
    "TDNET_PROVIDER_SCHEMA_VERSION",
    "TdnetDiscStatus",
    "TdnetDocumentMetadata",
    "extract_retrieval_cursor_fields",
    "parse_tdnet_documents_list_payload",
]
