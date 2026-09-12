"""Company IR Raw Fetch Result -> `DisclosureDocument` + Company IR固有Metadata
(Phase4B-4)。

## Provider-neutral Common Coreへは含めないCompany IR固有情報

`DisclosureDocument`(`lib.disclosures.model`)はTDnet/EDINET/Company IRで
共有するProvider-neutralなSchemaであり、Company IR固有のField名を持ち込ま
ない(EDINET/TDnetと同じ境界原則)。Company IR固有の確認済みFieldは
`CompanyIrDocumentMetadata`という別のDataclassへ保持する。

## このModuleが意図的にやらないこと

- **`document_kind`の自動分類**: HTML/PDF本文を解析してDocumentKindを
  推測することは行わない(本文Semantic Extractionの禁止、Section 16)。
  常に`DocumentKind.UNKNOWN`とする。
- **`market_public_at`の自動抽出**: HTML本文・PDF内の日付文字列を
  Parseして`market_public_at`を構築することは行わない。呼び出し側が
  既に確認済みの正確なTimestamp(tz-aware)を明示的に渡した場合のみ
  設定する。日付のみで時刻が不明な場合、時刻を推測して埋めることを
  禁止する(呼び出し側が`market_public_at=None`のまま渡すことを想定)。
- **`provider_available_at`への`Last-Modified`のMapping**: HTTP
  `Last-Modified`ヘッダはOpaqueな観測値として`CompanyIrDocumentMetadata.
  http_last_modified_raw`へ保持するのみで、`provider_available_at`
  (またはその`basis`)へは一切変換しない。このModuleに`Last-Modified`
  からTimestampをParseするCodeパス自体が存在しない(誤用の余地を構造的に
  無くす)。
- **`entity_id`の推測**: 会社名文字列やURL Domainだけから`entity_id`
  (Ticker/Code)を機械的に決め打ちしない。呼び出し側が既存Entity
  Registry等で確認済みの`entity_id`を渡した場合のみ設定する(既定
  `None`)。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from lib.disclosures.model import NORMALIZER_VERSION, DisclosureDocument, DocumentKind
from lib.disclosures.providers.company_ir import ComplianceCheckResult
from lib.evidence.model import AvailabilityBasis

COMPANY_IR_NORMALIZER_VERSION = f"{NORMALIZER_VERSION}+COMPANY_IR_V1"


@dataclass(kw_only=True, frozen=True)
class CompanyIrDocumentMetadata:
    """Company IR固有の確認済みMetadata(Common Coreへは持ち込まない)。

    `http_last_modified_raw`は`str | None`のOpaque値であり、`datetime`へ
    変換しない(意図的 — Provider Timestampとして解釈可能だと誤解させない
    ための型上の区別)。
    """

    document_internal_id: str
    requested_url: str
    final_url: str
    requested_domain: str
    final_domain: str
    redirect_chain: tuple[dict[str, object], ...]
    http_status: int
    content_type_raw: str | None
    content_length_observed: int
    etag_raw: str | None
    http_last_modified_raw: str | None
    compliance: ComplianceCheckResult


def build_company_ir_document(
    fetch_payload: dict[str, object],
    *,
    internal_document_id: str,
    title: str,
    retrieved_at: datetime,
    entity_id: str | None = None,
    market_public_at: datetime | None = None,
    market_public_at_basis: AvailabilityBasis = AvailabilityBasis.UNKNOWN,
    raw_snapshot_ref: str | None = None,
    provenance_id: str | None = None,
) -> tuple[DisclosureDocument, CompanyIrDocumentMetadata]:
    """`CompanyIrAdapter.fetch_document_raw()`が返した`RawFetchResult.payload`
    (またはSnapshot再読込後の同形状dict)から、`DisclosureDocument`と
    `CompanyIrDocumentMetadata`を構築する。

    `market_public_at`を渡さない場合、`market_public_at_basis`は強制的に
    `UNKNOWN`となる(値が無いのに確信度だけ高いという矛盾状態を防ぐ)。
    値を渡す場合も、呼び出し側が明示的に`market_public_at_basis=
    AvailabilityBasis.EXACT`等を指定しない限り既定`UNKNOWN`のままとする
    (「値が取得できた」ことと「確信度が高い」ことは別軸、Section 14-1)。

    `provider_available_at`はこの関数のSignatureにすら存在しない
    (常に`None`/`UNKNOWN`固定) — Last-Modified等からの誤ったMappingが
    構造的に起こりえない設計。
    """
    if market_public_at is None and market_public_at_basis != AvailabilityBasis.UNKNOWN:
        raise ValueError("market_public_atが無いのにmarket_public_at_basisをUNKNOWN以外にはできません")
    if market_public_at is not None and market_public_at.tzinfo is None:
        raise ValueError("market_public_at はtz-awareである必要があります")

    headers = fetch_payload.get("headers")
    if not isinstance(headers, dict):
        headers = {}
    compliance_raw = fetch_payload.get("compliance")
    if not isinstance(compliance_raw, dict):
        raise ValueError("fetch_payloadにcompliance情報が含まれていません(CompanyIrAdapter経由の取得結果を渡してください)")

    from lib.disclosures.providers.company_ir import ComplianceStatus, assert_retrieval_allowed

    compliance = ComplianceCheckResult(
        terms_checked=bool(compliance_raw["terms_checked"]),
        robots_checked=bool(compliance_raw["robots_checked"]),
        automated_retrieval=ComplianceStatus(compliance_raw["automated_retrieval"]),
        redistribution=ComplianceStatus(compliance_raw["redistribution"]),
        retention=ComplianceStatus(compliance_raw["retention"]),
        attribution_required=ComplianceStatus(compliance_raw["attribution_required"]),
        checked_by=str(compliance_raw["checked_by"]),
        checked_at=datetime.fromisoformat(str(compliance_raw["checked_at"])),
        notes=str(compliance_raw.get("notes", "")),
    )
    # Defense in depth(pit-auditor Finding、Phase4B-4): fetch_payloadが
    # 実際に`CompanyIrAdapter.fetch_document_raw()`を経由していれば
    # ここでautomated_retrieval != ALLOWEDになることは無いはずだが、
    # 手組みのfetch_payload dictを渡された場合に備えて正規化時にも
    # 再度Fail Closedを確認する(RAW-001/SOURCE-001と同じ「構造的に
    # 誤用不可能にする」設計方針をNormalizer側にも適用)。
    assert_retrieval_allowed(compliance)

    redirect_chain_raw = fetch_payload.get("redirect_chain")
    redirect_chain = tuple(redirect_chain_raw) if isinstance(redirect_chain_raw, list) else ()

    metadata = CompanyIrDocumentMetadata(
        document_internal_id=internal_document_id,
        requested_url=str(fetch_payload["requested_url"]),
        final_url=str(fetch_payload["final_url"]),
        requested_domain=str(fetch_payload["requested_domain"]),
        final_domain=str(fetch_payload["final_domain"]),
        redirect_chain=redirect_chain,
        http_status=int(str(fetch_payload["http_status"])),
        content_type_raw=headers.get("Content-Type"),
        content_length_observed=int(str(fetch_payload["content_length_observed"])),
        etag_raw=headers.get("ETag"),
        http_last_modified_raw=headers.get("Last-Modified"),
        compliance=compliance,
    )

    document = DisclosureDocument(
        internal_document_id=internal_document_id,
        source_document_id=None,
        entity_id=entity_id,
        title=title,
        document_kind=DocumentKind.UNKNOWN,
        originating_source="COMPANY_IR",
        delivery_provider="COMPANY_IR",
        market_public_at=market_public_at,
        market_public_at_basis=market_public_at_basis,
        provider_available_at=None,
        provider_available_at_basis=AvailabilityBasis.UNKNOWN,
        retrieved_at=retrieved_at,
        source_version=None,
        raw_snapshot_ref=raw_snapshot_ref,
        language=None,
        attachments=(),
        provenance_id=provenance_id,
        normalizer_version=COMPANY_IR_NORMALIZER_VERSION,
    )
    return document, metadata


__all__ = ["CompanyIrDocumentMetadata", "COMPANY_IR_NORMALIZER_VERSION", "build_company_ir_document"]
