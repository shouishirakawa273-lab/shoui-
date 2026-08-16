"""Fundamental MetricからEvidenceを作る(Phase4A、D0043)。

Phase4Aでは「業績が良い」「Positive」「買い」等の解釈は禁止する。作れるのは
FACTのみ(例:「2024-08-09に会社がFY営業利益予想を100→120へ変更した」まで)。
「これはBullish」は作らない。`EvidenceRelation`(SUPPORTS/CONTRADICTS等)も、
Hypothesisが存在しない限り付与しない(RESEARCH_RULES.md「0.5」参照、DEFAULT
PROCESS = ADVERSARIAL、CONCLUSION = NEUTRAL UNTIL SUPPORTED)。
"""

from __future__ import annotations

from datetime import datetime

from lib.evidence.model import DataLayer, EvidenceRecord, EvidenceType
from lib.fundamentals.model import DisclosureEnvelope, FundamentalMetric
from lib.sources.catalog import DataCapability, PrimaryOrSecondary, SourceAuthorityClass, SourceMetadata


def disclosure_metric_to_evidence(envelope: DisclosureEnvelope, metric: FundamentalMetric) -> EvidenceRecord:
    """開示された値そのものをFACTとして記述するのみ(解釈を加えない)。

    `source.available_at`には`envelope.market_public_at`(無ければ`envelope.
    retrieved_at`)を使う。これはReproducible System Simulation(B系統)の
    観点では保守的な選択である: market_public_atはprovider_available_at以前
    (=Providerがそれより先に配信することはない)であるため、`available_at`を
    過大評価(実際より早く使えたと誤認)することはない。一方、Fundamental Metric
    自体のRevision管理(`SourceVersion.availability_basis`)ほど厳密な
    UNKNOWN除外機構は`EvidenceRecord`には無い(既存D0040 Schemaの制約、
    `EVIDENCE_MODEL.md`参照)ため、厳密なB系統PIT判定には
    `lib.fundamentals.view.fundamentals_as_of()`を使うこと。
    """
    value_display = metric.raw_value if metric.raw_value is not None else metric.value_availability.value
    content = (
        f"{envelope.internal_code}: {metric.metric_type}"
        f"({metric.fiscal_year_target.value}, {metric.period_type.value}, "
        f"{metric.actual_or_forecast.value}, {metric.consolidation_scope.value})を"
        f"{value_display}として開示(disclosure_number={envelope.disclosure_number})"
    )
    available_at: datetime = envelope.market_public_at or envelope.retrieved_at
    source = SourceMetadata(
        source_id=envelope.envelope_id,
        source_type="JQUANTS_FINS_SUMMARY",
        provider_name="J-Quants",
        source_authority_class=SourceAuthorityClass.COMPANY_PRIMARY,
        primary_or_secondary=PrimaryOrSecondary.PRIMARY,
        retrieved_at=envelope.retrieved_at,
        published_at=envelope.market_public_at,
        available_at=available_at,
        originating_source="JQUANTS_SOURCE_DATA",  # 公式仕様で確認できた範囲のみ(D0043、DATA_SOURCE_ARCHITECTURE.md参照)
        delivery_provider="JQUANTS",
        provenance_id=envelope.provenance_id,
    )
    return EvidenceRecord(
        evidence_id=f"EVID_{metric.metric_id}",
        evidence_type=EvidenceType.FACT,
        layer=DataLayer.NORMALIZED,
        capability=DataCapability.FUNDAMENTAL,
        content=content,
        source=source,
        related_codes=(envelope.internal_code,),
        provenance_id=envelope.provenance_id,
    )
