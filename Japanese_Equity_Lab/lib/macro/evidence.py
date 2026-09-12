"""Macro MetricからEvidenceを作る(Phase4D)。

「CPI上昇率が高いのでInflation Pressureが強い」のようなInterpretation/
Predictionは一切生成しない。作れるのはFACTのみ(例:「JP CPI Headlineの
2026年7月分は+X%として記録された」まで)。Positive/Negative/Hawkish/
Dovish/利上げ/景気後退等の解釈語はここでは一切使わない(Phase4D要件§2/§40、
`lib.evidence.model`のDEFAULT PROCESS = ADVERSARIAL / CONCLUSION = NEUTRAL
UNTIL SUPPORTED原則)。

`lib.positioning.evidence.positioning_record_to_evidence()`/`lib.
fundamentals.evidence.disclosure_metric_to_evidence()`と同じD0049/D0050
PIT Bugfix方針を踏襲する: `source.available_at`には常に`record.retrieved_at`
(Observed Safe Availability Timestamp、正確なProvider Availabilityそのもの
ではない下限)を使い、`market_public_at`へのFallbackは行わない。厳密な
PIT判定には`lib.macro.view.macro_as_of()`を使うこと。
"""

from __future__ import annotations

from lib.evidence.model import DataLayer, EvidenceRecord, EvidenceType
from lib.macro.model import MacroRecord
from lib.sources.catalog import DataCapability, PrimaryOrSecondary, SourceAuthorityClass, SourceMetadata


def macro_record_to_evidence(
    record: MacroRecord,
    *,
    source_authority_class: SourceAuthorityClass,
    originating_source: str,
    delivery_provider: str,
) -> EvidenceRecord:
    """公表/確認された値そのものをFACTとして記述するのみ(解釈を加えない)。"""
    value_display = record.raw_value if record.raw_value is not None else record.value_availability.value
    period_display = (
        record.reference_period_start.isoformat()
        if record.reference_period_start == record.reference_period_end
        else f"{record.reference_period_start.isoformat()}〜{record.reference_period_end.isoformat()}"
    )
    content = (
        f"{record.series_id}: {record.metric_name}({period_display}, {record.frequency.value}, "
        f"{record.seasonal_adjustment.value})={value_display}"
    )
    # market_public_atへはFallbackしない(Fundamentals D0049/D0050・Positioning Phase4Cと同じ方針)。
    source = SourceMetadata(
        source_id=record.record_id,
        source_type=record.source_id,
        provider_name=record.source_id,
        source_authority_class=source_authority_class,
        primary_or_secondary=PrimaryOrSecondary.PRIMARY,
        retrieved_at=record.retrieved_at,
        published_at=record.market_public_at,
        available_at=record.retrieved_at,
        originating_source=originating_source,
        delivery_provider=delivery_provider,
        provenance_id=record.provenance_id,
    )
    return EvidenceRecord(
        evidence_id=f"EVID_{record.record_id}",
        evidence_type=EvidenceType.FACT,
        layer=DataLayer.NORMALIZED,
        capability=DataCapability.MACRO,
        content=content,
        source=source,
        value_date=record.reference_period_end,
        provenance_id=record.provenance_id,
    )
