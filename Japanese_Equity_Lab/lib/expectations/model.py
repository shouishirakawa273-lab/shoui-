"""Market Expectations Foundation: Core Record Types(D0108)。

**本Moduleは市場参加者の期待を直接観測できる単一の真実として表現しない**
(D0108 §2)。「市場はX%の成長を期待している」という単一の主張は一切
構築しない——常に3つの別概念を明確に分離して保持する:

- **OBSERVED EXPECTATION PROXY**(`ExpectationObservation`/
  `ConsensusSnapshot`): Analyst Consensus・Company Guidance等、外部から
  観測されたProxy。
- **MARKET-IMPLIED ASSUMPTION**(`lib.expectations.reverse_spec`):
  固定Assumption群の下で現在価格と整合する値。
- **RESEARCH FORECAST**(既存`lib.evaluation.model.PredictionRecord`、
  D0107、複製しない)。

## Consensus != Truth(既存`lib.consensus.model.ConsensusRecord`の再利用)

既存`lib.consensus.model.ConsensusRecord`が既にAnalyst Consensusを
PIT-safe/vintage-aware/source-aware/provenance-preservingな形で表現
している(Phase4E-4)。本Moduleはこれを複製しない——`ConsensusSnapshot`
は`ConsensusRecord`から構築する薄いAdapterであり、D0107の`record_hash`
Tamper Evidenceパターンをその上に追加するのみ(D0108 §4、新しい
Ingestion/Normalization機構は作らない)。

## Company Guidance(既存`lib.fundamentals.model.FundamentalMetric`の再利用)

Company Guidanceも既存`lib.fundamentals.model.FundamentalMetric`
(`actual_or_forecast=ActualOrForecast.COMPANY_FORECAST`)が既に表現して
いる。本Moduleはこれを複製しない——Analyst ConsensusとCompany Guidance
を同じ型へ潰さない(D0108 §15、`observation_from_company_forecast_
metric()`が`actual_or_forecast`を検証し、ACTUAL Metricの混入を拒否
する)。

## PIT(D0108 §6)

`available_at > decision_at`のObservationはComparison(`lib.expectations.
comparison`)で使用禁止——Unknown PIT FieldからのFallbackは行わない
(既存`lib.evidence`/`lib.consensus`/`lib.fundamentals`と同じ原則)。
Snapshot/Observation自体の構築時にはPIT Gateを課さない(構築時点では
`decision_at`が未定のことがあるため、Gateは消費側=Comparison時点で
行う、D0108 §6の最終文「...may be used in comparison」に対応)。

## Single-Estimate != Broad Consensus(D0108 §17/§21G)

`ConsensusCoverageStatus`(SINGLE_ESTIMATE/LIMITED_COVERAGE/
BROAD_COVERAGE/UNKNOWN_COVERAGE)により、1件のAnalyst Estimateが暗黙に
「広範な市場Consensus」へ格上げされることを防ぐ。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from lib.consensus.model import ConsensusRecord
from lib.evaluation.integrity import compute_record_hash
from lib.evidence.research_artifact import DataGap, DataGapStatus
from lib.fundamentals.model import ActualOrForecast, FundamentalMetric


class MarketExpectationsSchemaError(ValueError):
    """本Module固有のSchema/Invariant違反(呼び出し側のProgramming
    Errorに相当するもの)で送出する(D0103-D0107と同じ方針)。PIT違反は
    専用の既存`lib.errors.LookAheadBiasError`を使う(本Errorとは区別
    する、`lib.expectations.comparison`参照)。"""


class ExpectationProxyCategory(StrEnum):
    """観測されたMarket Expectation Proxyの種別(D0108 §5)。いずれも
    「市場の期待そのもの」ではなく、特定Sourceからの特定種類のProxyで
    あることを型で強制する。"""

    ANALYST_CONSENSUS = "ANALYST_CONSENSUS"
    COMPANY_GUIDANCE = "COMPANY_GUIDANCE"
    PRICE_IMPLIED = "PRICE_IMPLIED"
    PEER_IMPLIED = "PEER_IMPLIED"
    OTHER_EXPLICIT_PROXY = "OTHER_EXPLICIT_PROXY"


class StalenessStatus(StrEnum):
    """ExpectationObservationが現在の意思決定に使ってよい新鮮さを保って
    いるか(D0108 §18)。投資上の重要性はここでは判定しない(`policy`は
    呼び出し側が`max_age_days`として明示する)。"""

    FRESH = "FRESH"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class ConsensusCoverageStatus(StrEnum):
    """`estimate_count`から導出する被覆状態(D0108 §17/§21G)。1件の
    Estimateを暗黙に「広範なConsensus」へ格上げしない。"""

    SINGLE_ESTIMATE = "SINGLE_ESTIMATE"
    LIMITED_COVERAGE = "LIMITED_COVERAGE"
    BROAD_COVERAGE = "BROAD_COVERAGE"
    UNKNOWN_COVERAGE = "UNKNOWN_COVERAGE"


def require_nonempty_str(value: str, *, label: str) -> None:
    if not isinstance(value, str) or not value:
        raise MarketExpectationsSchemaError(f"{label} は空でないstrである必要があります")


def require_tz_aware(value: datetime, *, label: str) -> None:
    if value.tzinfo is None:
        raise MarketExpectationsSchemaError(f"{label} はtz-awareである必要があります")


def classify_consensus_coverage(estimate_count: int | None, *, broad_coverage_minimum: int = 3) -> ConsensusCoverageStatus:
    """`estimate_count`からCoverage状態を決定論的に分類する(D0108 §17)。

    `estimate_count`が`None`(Provider未提供)の場合は`UNKNOWN_COVERAGE`
    (0件とは推測しない、`lib.consensus.model`の既存原則CONS-024と同じ)。
    `broad_coverage_minimum`未満は`SINGLE_ESTIMATE`/`LIMITED_COVERAGE`の
    いずれかに留め、無条件で`BROAD_COVERAGE`を主張しない。
    """
    if broad_coverage_minimum < 2:
        raise MarketExpectationsSchemaError("broad_coverage_minimum は2以上である必要があります")
    if estimate_count is None:
        return ConsensusCoverageStatus.UNKNOWN_COVERAGE
    if estimate_count < 0:
        raise MarketExpectationsSchemaError("estimate_count は0以上である必要があります")
    if estimate_count <= 1:
        return ConsensusCoverageStatus.SINGLE_ESTIMATE
    if estimate_count < broad_coverage_minimum:
        return ConsensusCoverageStatus.LIMITED_COVERAGE
    return ConsensusCoverageStatus.BROAD_COVERAGE


def evaluate_staleness(observed_at: datetime, decision_at: datetime, *, max_age_days: int | None) -> StalenessStatus:
    """`observed_at`から`decision_at`までの経過日数が`max_age_days`を
    超えるかを決定論的に判定する(D0108 §18)。`max_age_days`が`None`
    (Policy未指定)の場合は判定を推測せず`UNKNOWN`を返す。
    """
    require_tz_aware(observed_at, label="observed_at")
    require_tz_aware(decision_at, label="decision_at")
    if max_age_days is None:
        return StalenessStatus.UNKNOWN
    if max_age_days < 0:
        raise MarketExpectationsSchemaError("max_age_days は0以上である必要があります")
    age_days = (decision_at - observed_at).total_seconds() / 86400.0
    if age_days < 0:
        raise MarketExpectationsSchemaError(
            f"observed_at({observed_at.isoformat()})がdecision_at({decision_at.isoformat()})より後です"
        )
    return StalenessStatus.STALE if age_days > max_age_days else StalenessStatus.FRESH


def missing_expectation_data_gap(
    *, category: ExpectationProxyCategory, metric: str, target_period: str, status: DataGapStatus, note: str = ""
) -> DataGap:
    """Consensus/Expectation Proxyが取得できなかったことを、新しい
    DataGap概念を作らず既存`lib.evidence.research_artifact.DataGap`
    (D0108 §16「reuse an existing DataGap convention」)で明示的に表現
    する。Consensusを捏造しない——`value`を推測で埋めることは一切しない。
    """
    return DataGap(topic=f"EXPECTATION_PROXY:{category.value}:{metric}:{target_period}", status=status, note=note)


@dataclass(kw_only=True, frozen=True)
class ConsensusSnapshot:
    """特定PIT Cutoff時点で外部から観測されたConsensus Data(D0108 §4)。

    既存`lib.consensus.model.ConsensusRecord`から`build_consensus_
    snapshot()`経由でのみ構築する(新しいConsensus Ingestion機構は
    作らない)。`source_consensus_record_id`により元の`ConsensusRecord`
    へ常に遡及できる(Provenance、D0108 §4「tamper-evident where
    consistent with D0107」)。
    """

    consensus_snapshot_id: str
    entity_id: str
    metric: str
    target_period: str
    value: Decimal
    unit: str | None
    source_id: str
    provider: str
    provider_version: str | None
    estimate_count: int | None
    dispersion: Decimal | None
    coverage_status: ConsensusCoverageStatus
    observed_at: datetime
    available_at: datetime
    source_consensus_record_id: str
    created_at: datetime
    record_hash: str

    def __post_init__(self) -> None:
        for name, value in (
            ("consensus_snapshot_id", self.consensus_snapshot_id),
            ("entity_id", self.entity_id),
            ("metric", self.metric),
            ("target_period", self.target_period),
            ("source_id", self.source_id),
            ("provider", self.provider),
            ("source_consensus_record_id", self.source_consensus_record_id),
        ):
            require_nonempty_str(value, label=name)
        require_tz_aware(self.observed_at, label="observed_at")
        require_tz_aware(self.available_at, label="available_at")
        require_tz_aware(self.created_at, label="created_at")
        if self.estimate_count is not None and self.estimate_count < 0:
            raise MarketExpectationsSchemaError("estimate_count は0以上である必要があります")


def _consensus_target_period_identity(record: ConsensusRecord) -> str:
    if record.provider_target_period_id:
        return record.provider_target_period_id
    if record.target_period_start is not None and record.target_period_end is not None:
        return f"{record.target_period_start.isoformat()}..{record.target_period_end.isoformat()}"
    raise MarketExpectationsSchemaError(
        f"ConsensusRecord(record_id={record.record_id!r}) に target_period を識別できるFieldが"
        "ありません(provider_target_period_id/target_period_start+end のいずれも未設定)"
    )


def build_consensus_snapshot(
    *,
    consensus_snapshot_id: str,
    source_record: ConsensusRecord,
    created_at: datetime,
    broad_coverage_minimum: int = 3,
    dispersion: Decimal | None = None,
) -> ConsensusSnapshot:
    """`ConsensusRecord`から`ConsensusSnapshot`を構築する唯一の
    Entrypoint(D0108 §4)。

    `source_record.entity_id`が`None`(Ambiguous Entity Mapping、
    `lib.consensus.model`の既存Fail Closed原則)の場合、または`value`/
    `provider_available_at`が未確定の場合は、Fallbackや推測を行わず
    `MarketExpectationsSchemaError`で拒否する(D0108 §6「No fallback
    from unavailable PIT fields」)。
    """
    if source_record.entity_id is None:
        raise MarketExpectationsSchemaError(
            f"ConsensusRecord(record_id={source_record.record_id!r}) の entity_id が未確定"
            "(Ambiguous Entity Mapping)のため ConsensusSnapshot を構築できません"
        )
    if source_record.value is None:
        raise MarketExpectationsSchemaError(
            f"ConsensusRecord(record_id={source_record.record_id!r}) の value が未確定のため"
            " ConsensusSnapshot を構築できません(推測で埋めない)"
        )
    if source_record.provider_available_at is None:
        raise MarketExpectationsSchemaError(
            f"ConsensusRecord(record_id={source_record.record_id!r}) の provider_available_at が"
            "未確定のため ConsensusSnapshot を構築できません(published_at等へのFallback禁止)"
        )
    target_period = _consensus_target_period_identity(source_record)
    coverage_status = classify_consensus_coverage(source_record.analyst_count, broad_coverage_minimum=broad_coverage_minimum)
    payload = {
        "consensus_snapshot_id": consensus_snapshot_id,
        "entity_id": source_record.entity_id,
        "metric": source_record.metric_type,
        "target_period": target_period,
        "value": source_record.value,
        "unit": source_record.unit,
        "source_id": source_record.source_id,
        "provider": source_record.source_id,
        "provider_version": source_record.normalizer_version,
        "estimate_count": source_record.analyst_count,
        "dispersion": dispersion,
        "coverage_status": coverage_status,
        "observed_at": source_record.retrieved_at,
        "available_at": source_record.provider_available_at,
        "source_consensus_record_id": source_record.record_id,
        "created_at": created_at,
    }
    return ConsensusSnapshot(
        consensus_snapshot_id=consensus_snapshot_id,
        entity_id=source_record.entity_id,
        metric=source_record.metric_type,
        target_period=target_period,
        value=source_record.value,
        unit=source_record.unit,
        source_id=source_record.source_id,
        provider=source_record.source_id,
        provider_version=source_record.normalizer_version,
        estimate_count=source_record.analyst_count,
        dispersion=dispersion,
        coverage_status=coverage_status,
        observed_at=source_record.retrieved_at,
        available_at=source_record.provider_available_at,
        source_consensus_record_id=source_record.record_id,
        created_at=created_at,
        record_hash=compute_record_hash(payload),
    )


@dataclass(kw_only=True, frozen=True)
class ExpectationObservation:
    """汎用Market Expectation Proxy(D0108 §5)。`category`により
    Analyst Consensus/Company Guidance/Price-Implied/Peer-Implied/
    Other-Explicit-Proxyを明確に区別し、互いに混同しない。
    """

    observation_id: str
    category: ExpectationProxyCategory
    entity_id: str
    metric: str
    target_period: str
    value: Decimal
    unit: str
    currency: str | None
    source_id: str
    observed_at: datetime
    available_at: datetime
    staleness_status: StalenessStatus
    provenance_ref: str
    created_at: datetime
    record_hash: str

    def __post_init__(self) -> None:
        for name, value in (
            ("observation_id", self.observation_id),
            ("entity_id", self.entity_id),
            ("metric", self.metric),
            ("target_period", self.target_period),
            ("unit", self.unit),
            ("source_id", self.source_id),
            ("provenance_ref", self.provenance_ref),
        ):
            require_nonempty_str(value, label=name)
        if not isinstance(self.category, ExpectationProxyCategory):
            raise MarketExpectationsSchemaError(f"category は ExpectationProxyCategory である必要があります: {self.category!r}")
        require_tz_aware(self.observed_at, label="observed_at")
        require_tz_aware(self.available_at, label="available_at")
        require_tz_aware(self.created_at, label="created_at")


def build_expectation_observation(
    *,
    observation_id: str,
    category: ExpectationProxyCategory,
    entity_id: str,
    metric: str,
    target_period: str,
    value: Decimal,
    unit: str,
    source_id: str,
    observed_at: datetime,
    available_at: datetime,
    provenance_ref: str,
    created_at: datetime,
    currency: str | None = None,
    decision_at: datetime | None = None,
    staleness_max_age_days: int | None = None,
) -> ExpectationObservation:
    """`ExpectationObservation`を構築する唯一の汎用Entrypoint(D0108 §5)。

    `decision_at`を指定した場合のみStaleness(`evaluate_staleness()`)を
    計算する(`decision_at`未指定時は`StalenessStatus.UNKNOWN`のまま、
    推測しない)。本関数自体はPIT Gate(available_at > decision_at)を
    課さない——そのObservationをComparisonへ使う時点で`lib.expectations.
    comparison`がGateする(D0108 §6)。
    """
    staleness_status = (
        evaluate_staleness(observed_at, decision_at, max_age_days=staleness_max_age_days)
        if decision_at is not None
        else StalenessStatus.UNKNOWN
    )
    payload = {
        "observation_id": observation_id,
        "category": category,
        "entity_id": entity_id,
        "metric": metric,
        "target_period": target_period,
        "value": value,
        "unit": unit,
        "currency": currency,
        "source_id": source_id,
        "observed_at": observed_at,
        "available_at": available_at,
        "staleness_status": staleness_status,
        "provenance_ref": provenance_ref,
        "created_at": created_at,
    }
    return ExpectationObservation(
        observation_id=observation_id,
        category=category,
        entity_id=entity_id,
        metric=metric,
        target_period=target_period,
        value=value,
        unit=unit,
        currency=currency,
        source_id=source_id,
        observed_at=observed_at,
        available_at=available_at,
        staleness_status=staleness_status,
        provenance_ref=provenance_ref,
        created_at=created_at,
        record_hash=compute_record_hash(payload),
    )


def observation_from_consensus_snapshot(
    snapshot: ConsensusSnapshot,
    *,
    observation_id: str,
    created_at: datetime,
    decision_at: datetime | None = None,
    staleness_max_age_days: int | None = None,
) -> ExpectationObservation:
    """`ConsensusSnapshot`(Analyst Consensus)から`ExpectationObservation`
    を構築する(D0108 §5)。`category`は常に`ANALYST_CONSENSUS`に固定
    され、呼び出し側が誤って別Categoryへ分類することはできない。
    """
    if snapshot.unit is None:
        raise MarketExpectationsSchemaError(
            f"ConsensusSnapshot(consensus_snapshot_id={snapshot.consensus_snapshot_id!r}) の unit が"
            "未確定のため ExpectationObservation を構築できません"
        )
    return build_expectation_observation(
        observation_id=observation_id,
        category=ExpectationProxyCategory.ANALYST_CONSENSUS,
        entity_id=snapshot.entity_id,
        metric=snapshot.metric,
        target_period=snapshot.target_period,
        value=snapshot.value,
        unit=snapshot.unit,
        source_id=snapshot.source_id,
        observed_at=snapshot.observed_at,
        available_at=snapshot.available_at,
        provenance_ref=snapshot.consensus_snapshot_id,
        created_at=created_at,
        decision_at=decision_at,
        staleness_max_age_days=staleness_max_age_days,
    )


def observation_from_company_forecast_metric(
    metric: FundamentalMetric,
    *,
    observation_id: str,
    entity_id: str,
    target_period: str,
    observed_at: datetime,
    available_at: datetime,
    created_at: datetime,
    decision_at: datetime | None = None,
    staleness_max_age_days: int | None = None,
) -> ExpectationObservation:
    """`FundamentalMetric`(`actual_or_forecast=COMPANY_FORECAST`のみ)
    からCompany Guidance`ExpectationObservation`を構築する(D0108 §15)。

    `actual_or_forecast != COMPANY_FORECAST`(例: ACTUAL実績値)が渡さ
    れた場合は`MarketExpectationsSchemaError`で拒否する——Company
    GuidanceとAnalyst Consensus/実績値を取り違えない(D0108 §21C)。
    `available_at`/`observed_at`はCaller(既存`lib.fundamentals.view`/
    `SourceVersion`を参照できる側)が明示的に渡す——本Moduleは
    Fundamentals自身のPIT導出Logicを複製しない。
    """
    if metric.actual_or_forecast != ActualOrForecast.COMPANY_FORECAST:
        raise MarketExpectationsSchemaError(
            f"FundamentalMetric(metric_id={metric.metric_id!r}) の actual_or_forecast は"
            f"{metric.actual_or_forecast!r} であり、COMPANY_FORECAST ではないため Company Guidance"
            " として扱えません(Company Guidance != Analyst Consensus != Actual Result)"
        )
    if metric.value is None:
        raise MarketExpectationsSchemaError(
            f"FundamentalMetric(metric_id={metric.metric_id!r}) の value が未確定のため ExpectationObservation を構築できません"
        )
    if metric.unit is None:
        raise MarketExpectationsSchemaError(
            f"FundamentalMetric(metric_id={metric.metric_id!r}) の unit が未確定のため ExpectationObservation を構築できません"
            "(推測で埋めない)"
        )
    return build_expectation_observation(
        observation_id=observation_id,
        category=ExpectationProxyCategory.COMPANY_GUIDANCE,
        entity_id=entity_id,
        metric=metric.metric_type,
        target_period=target_period,
        value=metric.value,
        unit=metric.unit,
        source_id="COMPANY_GUIDANCE",
        observed_at=observed_at,
        available_at=available_at,
        provenance_ref=metric.metric_id,
        created_at=created_at,
        currency=metric.currency,
        decision_at=decision_at,
        staleness_max_age_days=staleness_max_age_days,
    )


__all__ = [
    "ConsensusCoverageStatus",
    "ConsensusSnapshot",
    "ExpectationObservation",
    "ExpectationProxyCategory",
    "MarketExpectationsSchemaError",
    "StalenessStatus",
    "build_consensus_snapshot",
    "build_expectation_observation",
    "classify_consensus_coverage",
    "evaluate_staleness",
    "missing_expectation_data_gap",
    "observation_from_company_forecast_metric",
    "observation_from_consensus_snapshot",
    "require_nonempty_str",
    "require_tz_aware",
]
