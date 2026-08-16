"""Provider-neutral Raw Payload -> `DisclosureDocument`/`DisclosureAttachment`(Phase4B-1、D0045)。

**重要: このPhaseは実Sourceへ接続しない。** 以下が読む「Raw Payload」は、
実在するTDnet/EDINET/Company IRのいずれの生Wire Formatも模したものではない
Provider-neutralなFixture専用Schemaである(`_KNOWN_DOC_KIND_MAP`のKeyも
すべてFixture専用の仮Provider Code)。実Source接続時(Phase4B-2以降)は、
`data-source-researcher` Subagentによる公式仕様確認を経てから、この
Provider-neutral Schemaへの実Mappingを追加すること。Field名を実Providerの
ものだと誤解しないこと。

Fixture Raw Payloadの想定Shape(1行 = 1 Disclosure Document):

```json
{
  "DocId": "FIXTURE-DOC-0001",
  "Code": "72030",
  "Title": "...",
  "DocKind": "FIXTURE_FINANCIAL_RESULTS",
  "PublicDate": "2024-05-08", "PublicTime": "15:30",
  "SourceVersion": "1",
  "Language": "ja",
  "Attachments": [{"AttachmentId": "...", "MediaType": "application/pdf",
                    "AttachmentKind": "PDF", "Filename": "...",
                    "Locator": "...", "IsPrimary": true}]
}
```

Rawからの変換方針は`lib.fundamentals.normalize`と同じ(D0043の教訓を継承):

- Empty StringをNoneへ変更しない。5桁Provider Code等は書き換えない。
- DocType(ここでは`DocKind`)文字列のsubstring heuristicで意味を推測しない。
  未知のProvider DocKindは`DocumentKind.UNKNOWN`へfail closedし、warningを
  残す。
- `market_public_at`はPublicDate+PublicTimeの両方が確認できた場合のみ
  tz-aware(Asia/Tokyo)構築する。時刻不明時は推測補完しない。
- `provider_available_at`は実観測ログが無いため常に`AvailabilityBasis.
  UNKNOWN`とする(Fundamentals Phase4Aと同じ保守的Anchor方式、D0043)。
  この2関数(`_build_market_public_at`/`_provider_available_at_and_basis`)
  は`lib.fundamentals.normalize`の同名Helperとロジックが同一だが、
  Phase4A実装済みコードへの機能変更を避けるためこのModule内に独立して
  再実装している(意図的、共有Module抽出は将来の低リスクなFollow-upとして
  据え置く)。
"""

from __future__ import annotations

import itertools
import logging
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from zoneinfo import ZoneInfo

from lib.data_sources.ticker_codes import TickerCodeNormalizationError, normalize_provider_code_to_internal
from lib.disclosures.model import (
    NORMALIZER_VERSION,
    AttachmentKind,
    DisclosureAttachment,
    DisclosureDocument,
    DocumentKind,
    DuplicateRelationKind,
    DuplicateSignal,
)
from lib.evidence.model import AvailabilityBasis
from lib.reproducibility import hash_json_safe
from lib.sources.entity_registry import EntityRegistry

logger = logging.getLogger(__name__)

_JST = ZoneInfo("Asia/Tokyo")

# Provider(Fixture専用、Provider-neutral) DocKind -> Common DocumentKind の
# 明示的Mapping(substring heuristic禁止)。実Sourceの値はまだ確認していない
# ため空に近い(未知はfail closed)。
_KNOWN_DOC_KIND_MAP: dict[str, DocumentKind] = {
    "FIXTURE_FINANCIAL_RESULTS": DocumentKind.FINANCIAL_RESULTS,
    "FIXTURE_FORECAST": DocumentKind.FORECAST,
    "FIXTURE_DIVIDEND": DocumentKind.DIVIDEND,
    "FIXTURE_CAPITAL_POLICY": DocumentKind.CAPITAL_POLICY,
    "FIXTURE_SHARE_REPURCHASE": DocumentKind.SHARE_REPURCHASE,
    "FIXTURE_M_AND_A": DocumentKind.M_AND_A,
    "FIXTURE_GOVERNANCE": DocumentKind.GOVERNANCE,
    "FIXTURE_SECURITIES_REPORT": DocumentKind.SECURITIES_REPORT,
    "FIXTURE_LARGE_SHAREHOLDING": DocumentKind.LARGE_SHAREHOLDING,
    "FIXTURE_MATERIAL_EVENT": DocumentKind.MATERIAL_EVENT,
    "FIXTURE_OTHER": DocumentKind.OTHER,
}

_KNOWN_ATTACHMENT_KIND_MAP: dict[str, AttachmentKind] = {
    "PDF": AttachmentKind.PDF,
    "XBRL": AttachmentKind.XBRL,
    "HTML": AttachmentKind.HTML,
    "CSV": AttachmentKind.CSV,
    "XML": AttachmentKind.XML,
}


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _parse_doc_kind(raw: object) -> DocumentKind:
    """未知のDocKindは例外にせず`UNKNOWN`へfail closedし、warningを残す
    (Provider Schema Change検出、Fundamentals Phase4Aと同じ方針)。"""
    if raw is None:
        return DocumentKind.UNKNOWN
    raw_str = str(raw)
    kind = _KNOWN_DOC_KIND_MAP.get(raw_str)
    if kind is None:
        logger.warning("disclosures: 未知のDocKind値 '%s' を検出しました(Provider Schema Changeの可能性)", raw_str)
        return DocumentKind.UNKNOWN
    return kind


def _parse_attachment_kind(raw: object) -> AttachmentKind:
    if raw is None:
        return AttachmentKind.UNKNOWN
    raw_str = str(raw)
    kind = _KNOWN_ATTACHMENT_KIND_MAP.get(raw_str)
    if kind is None:
        logger.warning("disclosures: 未知のAttachmentKind値 '%s' を検出しました", raw_str)
        return AttachmentKind.UNKNOWN
    return kind


def _parse_date_or_none(date_raw: str | None) -> date | None:
    """不正/欠損の`PublicDate`はNoneへfail closedする(pit-auditor Finding、
    D0045追記)。他のRaw Fieldと同じく、1行のParse失敗で全体の`parse_
    disclosure_payload`呼び出しを異常終了させない(即例外で全処理停止しない
    既存方針をこのFieldにも適用する)。"""
    if not date_raw:
        return None
    try:
        return date.fromisoformat(date_raw)
    except ValueError:
        logger.warning("disclosures: 不正なPublicDate値 '%s' を検出しました(この行のentity解決はスキップします)", date_raw)
        return None


def _build_market_public_at(date_raw: str | None, time_raw: str | None) -> tuple[datetime | None, AvailabilityBasis]:
    """PublicDate+PublicTimeからmarket_public_atを構築する。時刻不明時、
    15:00等を推測で補完しない(D0043と同じ方針)。"""
    if not date_raw or not time_raw:
        return None, AvailabilityBasis.UNKNOWN
    try:
        d = date.fromisoformat(date_raw)
        time_parts = time_raw.split(":")
        hour, minute = int(time_parts[0]), int(time_parts[1])
        dt = datetime(d.year, d.month, d.day, hour, minute, tzinfo=_JST)
    except (ValueError, IndexError):
        return None, AvailabilityBasis.UNKNOWN
    return dt, AvailabilityBasis.EXACT


def _provider_available_at_and_basis(
    market_public_at: datetime | None, retrieved_at: datetime
) -> tuple[datetime, AvailabilityBasis]:
    """実観測ログが無いため常に`AvailabilityBasis.UNKNOWN`とする
    (`market_public_at`をそのまま`provider_available_at`として確定事実
    扱いしない、D0043と同じ方針)。構造上必須のField自体には保守的な
    Anchorを入れる。"""
    anchor = market_public_at if market_public_at is not None else retrieved_at
    return anchor, AvailabilityBasis.UNKNOWN


def _parse_attachments(
    rows: Sequence[Mapping[str, object]], *, document_internal_id: str, retrieved_at: datetime
) -> list[DisclosureAttachment]:
    attachments: list[DisclosureAttachment] = []
    for index, row in enumerate(rows):
        attachment_id = _optional_str(row.get("AttachmentId")) or f"{document_internal_id}_ATT_{index}"
        attachments.append(
            DisclosureAttachment(
                attachment_id=attachment_id,
                document_internal_id=document_internal_id,
                source_attachment_id=_optional_str(row.get("AttachmentId")),
                media_type=_optional_str(row.get("MediaType")),
                attachment_kind=_parse_attachment_kind(row.get("AttachmentKind")),
                filename=_optional_str(row.get("Filename")),
                source_locator=_optional_str(row.get("Locator")),
                retrieved_at=retrieved_at,
                is_primary=bool(row.get("IsPrimary", False)),
            )
        )
    return attachments


def parse_disclosure_payload(
    payload: Sequence[Mapping[str, object]],
    *,
    retrieved_at: datetime,
    originating_source: str | None = None,
    delivery_provider: str | None = None,
    source_snapshot_id: str | None = None,
    entity_registry: EntityRegistry | None = None,
    entity_provider_name: str = "disclosure_fixture",
) -> list[DisclosureDocument]:
    """Provider-neutral Raw Payloadを`DisclosureDocument`(Attachments含む)へ
    変換する。正規化に失敗したProvider Code(普通株以外の可能性)はログ警告を
    出してスキップする(`lib.fundamentals.normalize.parse_financial_summary_
    payload`と同じ非厳格な扱い)。
    """
    documents: list[DisclosureDocument] = []

    for index, row in enumerate(payload):
        provider_code = _optional_str(row.get("Code"))
        internal_code: str | None = None
        if provider_code is not None:
            try:
                internal_code = normalize_provider_code_to_internal(provider_code)
            except TickerCodeNormalizationError:
                logger.warning(
                    "disclosures: provider_code=%s を内部Codeへ正規化できないためスキップします(普通株以外の可能性)",
                    provider_code,
                )
                continue

        doc_id_raw = _optional_str(row.get("DocId"))
        date_raw = _optional_str(row.get("PublicDate"))
        time_raw = _optional_str(row.get("PublicTime"))
        public_date = _parse_date_or_none(date_raw)
        market_public_at, market_public_at_basis = _build_market_public_at(date_raw, time_raw)
        provider_available_at, provider_available_at_basis = _provider_available_at_and_basis(market_public_at, retrieved_at)

        entity_id: str | None = None
        if entity_registry is not None and provider_code is not None and public_date is not None:
            mapping = entity_registry.resolve(
                provider_name=entity_provider_name, provider_identifier=provider_code, as_of=public_date
            )
            entity_id = mapping.issuer_id if mapping is not None else None

        # indexを常に使う(source_document_idはDedup検出のためRaw値のまま重複を
        # 許容する必要があるため、internal_document_idの一意性の根拠にしない)。
        internal_document_id = f"DOC_{internal_code or 'UNMAPPED'}_{index}"
        attachment_rows = row.get("Attachments")
        attachments = (
            _parse_attachments(attachment_rows, document_internal_id=internal_document_id, retrieved_at=retrieved_at)
            if isinstance(attachment_rows, list)
            else []
        )

        documents.append(
            DisclosureDocument(
                internal_document_id=internal_document_id,
                source_document_id=doc_id_raw,
                entity_id=entity_id,
                title=_optional_str(row.get("Title")) or "",
                document_kind=_parse_doc_kind(row.get("DocKind")),
                originating_source=originating_source,
                delivery_provider=delivery_provider,
                market_public_at=market_public_at,
                market_public_at_basis=market_public_at_basis,
                provider_available_at=provider_available_at,
                provider_available_at_basis=provider_available_at_basis,
                retrieved_at=retrieved_at,
                source_version=_optional_str(row.get("SourceVersion")),
                raw_snapshot_ref=source_snapshot_id,
                language=_optional_str(row.get("Language")),
                attachments=tuple(attachments),
                normalizer_version=NORMALIZER_VERSION,
            )
        )

    return documents


def find_exact_content_duplicate_groups(payload: Sequence[Mapping[str, object]]) -> dict[str, list[int]]:
    """Raw Payload内で、行全体のContent Hash(`lib.reproducibility.
    hash_json_safe`を再利用、独自Hash実装はしない)が完全一致する行の
    Indexをグルーピングする(例: Pagination境界での重複取得を検出する用途)。
    Hashが1件しかないGroupは返さない(重複候補のみ)。Titleや日付だけを見た
    Heuristic判定ではなく、行全体の完全一致のみを対象とする。
    """
    groups: dict[str, list[int]] = {}
    for i, row in enumerate(payload):
        content_hash = hash_json_safe(row)
        groups.setdefault(content_hash, []).append(i)
    return {content_hash: idxs for content_hash, idxs in groups.items() if len(idxs) > 1}


def find_same_source_document_id_signals(documents: Sequence[DisclosureDocument]) -> list[DuplicateSignal]:
    """同一`source_document_id`を持つ複数`DisclosureDocument`をDuplicate候補
    として検出する。**Title/PublicDate/Codeが同じというだけでは検出しない**
    (それらはこの関数の入力に一切使われない、意図的な構造上の制約)。"""
    by_source_id: dict[str, list[str]] = {}
    for document in documents:
        if document.source_document_id:
            by_source_id.setdefault(document.source_document_id, []).append(document.internal_document_id)

    signals: list[DuplicateSignal] = []
    for source_id, internal_ids in by_source_id.items():
        if len(internal_ids) < 2:
            continue
        for doc_a, doc_b in itertools.combinations(sorted(internal_ids), 2):
            signals.append(
                DuplicateSignal(
                    document_a_id=doc_a,
                    document_b_id=doc_b,
                    relation_kind=DuplicateRelationKind.SAME_SOURCE_DOCUMENT_ID,
                    basis=f"source_document_id={source_id}",
                )
            )
    return signals


__all__ = [
    "NORMALIZER_VERSION",
    "find_exact_content_duplicate_groups",
    "find_same_source_document_id_signals",
    "parse_disclosure_payload",
]
