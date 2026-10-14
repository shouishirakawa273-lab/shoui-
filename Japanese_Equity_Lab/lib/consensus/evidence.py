"""ConsensusRecordからEvidenceを作る(Phase4E-4)。

**Core Principleの再確認**: 作れるのは「特定Providerが特定時点でこの
Consensus値を報告していた」というPublication/Provider Observation Fact
のみ。Consensus値そのものをTruthや市場全体の期待として解釈しない
(Consensus != Truth、Phase4E-4要件§6)。Actual結果との比較(Beat/Miss/
Surprise)、Priced-in判定、Investment Conclusion(BUY/SELL)はこのModule
のいずれのFunctionも生成しない(Phase4E-4要件§30/§31)。

**D0057との境界(最重要、必読)**: この関数が返す`EvidenceRecord`は
`lib.evidence.retrieval.filter_usable_at()`等のEvidence経路PIT判定に
技術的には使用可能だが、**このRoundではBacktest/Decision Engineへ一切
接続しない**(Phase4E-4要件§43)。D0057(ARCHITECTURE_GAP、Validation
Backlog #21)が確認した通り、Evidence経路の`available_at`(常に`retrieved_
at`基準へFallbackしうる)と`lib.consensus.view.consensus_as_of()`の
Canonical Vintage Semanticsは独立した推定戦略であり、両者を統合する
設計判断はこのRoundでは行わない。
"""

from __future__ import annotations

from datetime import datetime

from lib.consensus.model import ConsensusRecord
from lib.evidence.model import AvailabilityBasis, DataLayer, EvidenceRecord, EvidenceType
from lib.sources.catalog import DataCapability, PrimaryOrSecondary, SourceAuthorityClass, SourceMetadata


def consensus_record_to_evidence(
    record: ConsensusRecord,
    *,
    source_authority_class: SourceAuthorityClass,
    originating_source: str,
    delivery_provider: str,
) -> EvidenceRecord:
    """このProviderがこのConsensus値を報告していたという事実のみをFACTとして
    記述する(値の解釈を加えない)。

    `source.available_at`は`lib.news.evidence.news_article_to_evidence()`
    (D0049/D0050 PIT Bugfix方針の踏襲)と同じ優先順位で決定する: (1)
    `provider_available_at`が確認済み(`provider_available_at_basis !=
    AvailabilityBasis.UNKNOWN`)であればそれを使う、(2) 確認できなければ
    `record.retrieved_at`(Observed Safe Availability Timestamp)を使う。
    **`published_at`/`provider_stated_as_of`へは決してFallbackしない**
    (Phase4E-4要件§14、consensus_as_ofの意味はSource-specificで統一的な
    Provider Availabilityの代用にならないため)。
    """
    if record.provider_available_at is not None and record.provider_available_at_basis != AvailabilityBasis.UNKNOWN:
        available_at: datetime = record.provider_available_at
    else:
        available_at = record.retrieved_at

    value_display = record.raw_value if record.raw_value is not None else record.value_availability.value
    period_display = (
        record.provider_target_period_id
        if record.provider_target_period_id is not None
        else (
            f"{record.target_period_start.isoformat()}〜{record.target_period_end.isoformat()}"
            if record.target_period_start is not None and record.target_period_end is not None
            else "取得不可"
        )
    )
    content = (
        f"{record.source_id}: {record.metric_type}({period_display}, {record.statistic_type.value}) "
        f"Consensus={value_display}" + (f", analysts={record.analyst_count}" if record.analyst_count is not None else "")
    )
    source = SourceMetadata(
        source_id=record.record_id,
        source_type=record.source_id,
        provider_name=record.source_id,
        source_authority_class=source_authority_class,
        primary_or_secondary=PrimaryOrSecondary.SECONDARY,
        retrieved_at=record.retrieved_at,
        published_at=record.published_at,
        available_at=available_at,
        originating_source=originating_source,
        delivery_provider=delivery_provider,
        provenance_id=record.provenance_id,
    )
    related_codes = () if record.entity_id is None else (record.entity_id,)
    return EvidenceRecord(
        evidence_id=f"EVID_CONSENSUS_{record.record_id}",
        evidence_type=EvidenceType.FACT,
        layer=DataLayer.NORMALIZED,
        capability=DataCapability.EXPECTATIONS,
        content=content,
        source=source,
        value_date=record.target_period_end,
        related_codes=related_codes,
        provenance_id=record.provenance_id,
    )


__all__ = ["consensus_record_to_evidence"]
