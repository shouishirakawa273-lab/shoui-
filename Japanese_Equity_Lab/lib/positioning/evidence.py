"""Positioning MetricからEvidenceを作る(Phase4C)。

「信用買残が積み上がっているから上値が重い」のようなInterpretation/Hypothesisは
一切生成しない。作れるのはFACT/DERIVED-FACTのみ(例:「7203の2026-08-18時点の
売買代金は12,345,678,900円と計算された」まで)。Positive/Negative/Bullish/
Bearish/Overhang/Crowding等の解釈語はここでは一切使わない(Phase4C要件§2/§36、
`lib.evidence.model`のDEFAULT PROCESS = ADVERSARIAL / CONCLUSION = NEUTRAL
UNTIL SUPPORTED原則)。

`lib.fundamentals.evidence.disclosure_metric_to_evidence()`と同じPIT Bugfix
方針(D0049/D0050)を踏襲する: `source.available_at`には常に`record.
retrieved_at`(Observed Factとしての安全な下限)を使い、`market_public_at`への
Fallbackは行わない。厳密なB系統PIT判定(Availability Basis考慮)には
`lib.positioning.view.positioning_as_of()`を使うこと。
"""

from __future__ import annotations

from lib.evidence.model import DataLayer, EvidenceRecord, EvidenceType
from lib.positioning.model import PositioningRecord
from lib.sources.catalog import DataCapability, PrimaryOrSecondary, SourceAuthorityClass, SourceMetadata


def positioning_record_to_evidence(
    record: PositioningRecord,
    *,
    layer: DataLayer,
    source_authority_class: SourceAuthorityClass,
    originating_source: str,
    delivery_provider: str,
) -> EvidenceRecord:
    """開示/計算された値そのものをFACT(または`DataLayer.DERIVED`の場合は
    Derived Fact)として記述するのみ(解釈を加えない)。

    `layer=DataLayer.DERIVED`(Price-derived Metric等、AI生成ではなく決定論的
    計算)を渡す場合、`ai_derived_provenance`は設定しない(`EvidenceRecord.
    __post_init__`はDERIVEDにAI Provenanceを要求しない、AI生成Derived Dataとは
    別の話)。
    """
    value_display = record.raw_value if record.raw_value is not None else record.value_availability.value
    period_display = (
        record.observation_start.isoformat()
        if record.observation_start == record.observation_end
        else f"{record.observation_start.isoformat()}〜{record.observation_end.isoformat()}"
    )
    content = f"{record.entity_code}: {record.metric_type}({period_display}, {record.frequency.value})={value_display}"
    # market_public_atへはFallbackしない(Fundamentals D0049/D0050 PIT Bugfixと同じ方針)。
    # このSchemaは確認済みprovider_available_atを保持するFieldを持たないため、
    # retrieved_at(Observed Factとしての下限)を常に使う。
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
        layer=layer,
        capability=DataCapability.POSITIONING,
        content=content,
        source=source,
        value_date=record.observation_end,
        related_codes=(record.entity_code,),
        provenance_id=record.provenance_id,
    )
