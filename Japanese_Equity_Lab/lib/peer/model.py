"""PIT-Safe Peer Comparison Foundation: 型定義(Stage 3.17、D0095)。

D0094が特定したDominant Research Bottleneck(Missing Cross-Sectional
Peer Context)を解消するための最初のArchitecture Roundである。このModule
自身は「どの銘柄がTarget EntityのPeerか」を一切ハードコードしない
(恣意的なPeer選定禁止、要件v1 §5)。

## Peer Comparisonが答える問い / 答えない問い(要件v1 §4)

答える: 「経済的に比較可能な企業群と比べ、Observable Metricsの上で
Research Timestamp時点でどう異なるか」。

答えない: 「どの銘柄が優れているか」。Research != Decision——
BUY/SELL/HOLD/Target Price/Position Sizingに相当するFieldはこの
Moduleのどこにも存在しない(構造的禁止、`lib.evidence.research_
artifact.ResearchArtifact`と同じ設計原則)。

## Candidate vs Accepted Peer(最重要区別、要件v1 §7)

`PeerCandidate`(第一段階、公式Classification一致のみ)と`AcceptedPeer`
(全Comparability Guardを通過)は別型として明確に分離する。S33等の
Sector Code一致だけでは「最終的な経済的に比較可能なPeer」を意味しない
——Comparability Guard(`lib.peer.comparability`)を経由して初めて
`AcceptedPeer`になる。Guardに落ちたCandidateは`ExcludedPeerCandidate`
として理由付きで可視のまま残す(Silent Dropを禁止する、要件v1 §8)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from lib.universe import UniverseResolution

# Stage 3.17(D0095)v1では東証33業種区分のみをClassification Systemとして
# 扱う(要件v1 §7の「First Eligibility Layer」)。他のClassification System
# (GICS等)は将来拡張の余地として`classification_system`をFree Stringに
# しているが、v1のBuilderはこの定数のみを生成する。
CLASSIFICATION_SYSTEM_TSE_SECTOR_33 = "TSE_SECTOR_33"

SELECTION_METHOD_SAME_TSE_SECTOR_33_CODE = "SAME_TSE_SECTOR_33_CODE"
SELECTION_VERSION_V1 = "v1"

# Comparability Guard(要件v1 §8 STALE_FINANCIAL_DATA)の閾値。「Peerの
# 最新FY実績Denominatorが、Targetの最新FY実績DenominatorよりFiscal
# Cycle換算で何年分遅れていたら明確にStaleとみなすか」というOperational
# Guardであり、統計的な主張ではない(`lib.valuation.model.
# MINIMUM_MONTHLY_OBSERVATIONS`と同じ「運用上の最低ライン」という位置
# づけ)。1(=1FY分の遅れまでは許容、2FY分以上遅れていればStale)。
STALE_FISCAL_CYCLE_THRESHOLD = 1

# Peer Aggregate Context(要件v1 §13)の最低Sample数。Historical Valuation
# ContextのMINIMUM_MONTHLY_OBSERVATIONS(12)と同じ「Operational Minimum
# であり統計的十分性の主張ではない」という位置づけだが、Peer Universeは
# 構造的にHistorical Monthly Anchorsよりはるかに小さい母集団になりうる
# ため、別の値として独立管理する(既存定数をSilentに転用しない)。
MINIMUM_PEER_SAMPLE_COUNT = 3


class PeerMetricType(StrEnum):
    """Stage 3.17 v1で実装するMetric Family(要件v1 §9、Compact Scope)。

    候補として許可されている6種類(要件v1 §9)のうち、v1では既存Production
    Builderで完全にEnd-to-Endの構築・Provenance・Testが揃っている2種類
    (Latest Reported FY PER・Current FY Company Forecast PER)のみを実装
    する。Sales/Operating Profit/Net Income/EPS YoYは、Builder自体は
    既存(`lib.fundamentals.same_period_yoy_builder`)だが、本Comparison
    Layerへの結線・Test Fixtureはこのラウンドでは行わない(Compactに保つ、
    要件v1 §9「v1 should remain compact」)——Enum自体は将来追加できるよう
    独立したMemberとして定義するが、存在しないMemberを先取りして定義する
    ことはしない(架空のReadinessを主張しない)。
    """

    LATEST_REPORTED_FY_PER = "LATEST_REPORTED_FY_PER"
    CURRENT_FY_COMPANY_FORECAST_PER = "CURRENT_FY_COMPANY_FORECAST_PER"


class PeerMetricAvailability(StrEnum):
    """1件のPeer Metric Observationの状態(要件v1 §11)。

    「値が無いこと」を0へ変換しない、という既存`ValueAvailability`/
    `DataGapStatus`と同じ思想を、Peer Metric専用の4値として明示する
    (要件v1 §11がAVAILABLE/MISSING/UNAVAILABLE/UNVERIFIEDという4値を
    明示的に要求しており、既存Enumはこの4値の組み合わせを持たないため
    新設する)。
    """

    AVAILABLE = "AVAILABLE"  # 値が存在し、as_of時点で参照可能
    MISSING = "MISSING"  # そもそも取得を試みていない/元Sourceが存在しない
    UNAVAILABLE = "UNAVAILABLE"  # 存在するはずだがas_of時点でまだ利用可能でない(PIT除外)
    UNVERIFIED = "UNVERIFIED"  # 取得できたが独立した確認が取れていない


class PeerExclusionReason(StrEnum):
    """Comparability Guardの排除理由(要件v1 §8、最低限8種類を型で保持)。"""

    SELF_PEER = "SELF_PEER"
    SECTOR_MISMATCH = "SECTOR_MISMATCH"
    CLASSIFICATION_UNAVAILABLE_PIT_SAFE = "CLASSIFICATION_UNAVAILABLE_PIT_SAFE"
    FISCAL_PERIOD_INCOMPARABLE = "FISCAL_PERIOD_INCOMPARABLE"
    ACCOUNTING_STANDARD_MISMATCH = "ACCOUNTING_STANDARD_MISMATCH"
    METRIC_UNAVAILABLE = "METRIC_UNAVAILABLE"
    STALE_FINANCIAL_DATA = "STALE_FINANCIAL_DATA"
    PRICE_UNAVAILABLE_AT_AS_OF = "PRICE_UNAVAILABLE_AT_AS_OF"
    ENTITY_IDENTITY_AMBIGUOUS = "ENTITY_IDENTITY_AMBIGUOUS"


@dataclass(kw_only=True, frozen=True)
class PeerCandidate:
    """First Eligibility Layer(要件v1 §7)を通過した1件のPeer Candidate。

    「同一Sector Code」であることのみを表し、経済的な比較可能性そのものは
    一切保証しない(`AcceptedPeer`とは明確に別型)。
    """

    entity_code: str
    provider_code: str | None
    company_name: str | None
    classification_system: str
    classification_code: str

    def __post_init__(self) -> None:
        if not self.entity_code:
            raise ValueError("entity_code は空にできません")


@dataclass(kw_only=True, frozen=True)
class PeerUniverseSnapshot:
    """Target Entity 1件についてのPeer Universe解決結果(要件v1 §5)。

    `lib.universe.UniverseResolution`をそのまま再利用する(既存Universe
    Infrastructureの再利用、要件v1 §6)——RESOLVED/PARTIAL/UNRESOLVED/
    DATA_UNAVAILABLEという同じ語彙を、Listing PITではなくClassification
    PITについて使う。
    """

    target_entity_code: str
    as_of: datetime
    classification_system: str
    target_classification_code: str | None
    candidates: tuple[PeerCandidate, ...] = field(default_factory=tuple)
    selection_method: str = SELECTION_METHOD_SAME_TSE_SECTOR_33_CODE
    selection_version: str = SELECTION_VERSION_V1
    resolution: UniverseResolution = UniverseResolution.DATA_UNAVAILABLE
    classification_snapshot_as_of: date | None = None
    pit_note: str = ""

    def __post_init__(self) -> None:
        if self.as_of.tzinfo is None:
            raise ValueError("as_of はtz-awareである必要があります")
        codes = [c.entity_code for c in self.candidates]
        if self.target_entity_code in codes:
            raise ValueError(
                f"target_entity_code({self.target_entity_code})がcandidatesへ混入しています"
                "(Self-Peer Exclusion Guard違反、fail closed)"
            )
        if len(set(codes)) != len(codes):
            duplicates = sorted({c for c in codes if codes.count(c) > 1})
            raise ValueError(f"candidatesにentity_codeの重複があります(Deterministic Membership違反): {duplicates}")
        if codes != sorted(codes):
            raise ValueError("candidatesはentity_code昇順でソートされている必要があります(Deterministic Ordering)")


@dataclass(kw_only=True, frozen=True)
class ExcludedPeerCandidate:
    """Comparability Guardで排除された1件のCandidate(要件v1 §8)。

    Silent Dropを禁止する——排除された事実と理由を必ず可視のまま保持する。
    """

    entity_code: str
    reasons: tuple[PeerExclusionReason, ...]
    note: str = ""

    def __post_init__(self) -> None:
        if not self.reasons:
            raise ValueError(f"entity_code={self.entity_code}: reasonsが空です(排除理由を必ず明示する)")
        if len(set(self.reasons)) != len(self.reasons):
            raise ValueError(f"entity_code={self.entity_code}: reasonsに重複があります")


@dataclass(kw_only=True, frozen=True)
class AcceptedPeer:
    """全Comparability Guardを通過した1件のPeer(要件v1 §7)。

    `PeerCandidate`とは別型——ここへ到達したEntityのみが実際のMetric
    比較(`PeerComparisonRecord`)へ進める。
    """

    entity_code: str
    classification_system: str
    classification_code: str
    as_of: datetime

    def __post_init__(self) -> None:
        if self.as_of.tzinfo is None:
            raise ValueError("as_of はtz-awareである必要があります")


@dataclass(kw_only=True, frozen=True)
class PeerEntityComparabilityResult:
    """Entity単位のComparability評価結果(Metric非依存のGuardのみ、要件v1 §7/§8)。

    `accepted`と`excluded`はどちらか一方のみが非Noneになる(Exactly-One
    Contract、両方Noneまたは両方値ありは許可しない)。
    """

    accepted: AcceptedPeer | None = None
    excluded: ExcludedPeerCandidate | None = None

    def __post_init__(self) -> None:
        if (self.accepted is None) == (self.excluded is None):
            raise ValueError("acceptedとexcludedはどちらか一方のみを設定する必要があります(Exactly-One Contract)")


@dataclass(kw_only=True, frozen=True)
class PeerMetricObservation:
    """1 Entity × 1 Metric × 1 as_ofについてのObservation(要件v1 §11)。

    Target/Peerを問わず同じ型を使う(`PeerComparisonRecord`が2つの
    Observationを対比する、要件v1 §10 Same-As-Of Rule)。
    """

    entity_code: str
    metric_type: PeerMetricType
    as_of: datetime
    availability: PeerMetricAvailability
    value: Decimal | None = None
    value_available_at: datetime | None = None
    fiscal_period_end: date | None = None
    accounting_standard: str | None = None
    source_evidence_id: str | None = None
    note: str = ""

    def __post_init__(self) -> None:
        if self.as_of.tzinfo is None:
            raise ValueError("as_of はtz-awareである必要があります")
        if self.availability == PeerMetricAvailability.AVAILABLE:
            if self.value is None:
                raise ValueError(f"entity_code={self.entity_code}: availability=AVAILABLEですがvalueがNoneです")
            if self.value_available_at is None:
                raise ValueError(f"entity_code={self.entity_code}: availability=AVAILABLEですがvalue_available_atがNoneです")
            if self.source_evidence_id is None:
                raise ValueError(f"entity_code={self.entity_code}: availability=AVAILABLEですがsource_evidence_idがNoneです")
            if self.value_available_at.tzinfo is None:
                raise ValueError("value_available_at はtz-awareである必要があります")
            if self.value_available_at > self.as_of:
                raise ValueError(
                    f"entity_code={self.entity_code}: value_available_at({self.value_available_at.isoformat()})が"
                    f"as_of({self.as_of.isoformat()})より後です(Same-As-Of Rule違反、PIT fail closed)"
                )
        else:
            if self.value is not None:
                raise ValueError(
                    f"entity_code={self.entity_code}: availability={self.availability.value}ですがvalueがNoneではありません"
                )
            if self.value_available_at is not None:
                raise ValueError(
                    f"entity_code={self.entity_code}: availability={self.availability.value}ですが"
                    "value_available_atがNoneではありません"
                )
            if self.source_evidence_id is not None:
                raise ValueError(
                    f"entity_code={self.entity_code}: availability={self.availability.value}ですが"
                    "source_evidence_idがNoneではありません"
                )


@dataclass(kw_only=True, frozen=True)
class PeerComparisonRecord:
    """Target 1件 × Peer 1件 × Metric 1件のComparison(要件v1 §12)。

    許可される記述の例(要件v1 §12): 「Toyota actual PER = X」「Peer
    actual PER = Y」「Difference = X-Y」。禁止される記述の例:
    「Toyota is cheap」「Toyota deserves rerating」——このRecordの
    どのFieldにもInterpretationを保持する余地は無い(単なる数値と
    Metadataのみ)。
    """

    target_entity_code: str
    peer_entity_code: str
    metric_type: PeerMetricType
    comparison_as_of: datetime
    target_observation: PeerMetricObservation
    peer_observation: PeerMetricObservation
    exclusion_reasons: tuple[PeerExclusionReason, ...] = field(default_factory=tuple)
    difference: Decimal | None = None

    def __post_init__(self) -> None:
        if self.comparison_as_of.tzinfo is None:
            raise ValueError("comparison_as_of はtz-awareである必要があります")
        if self.target_entity_code == self.peer_entity_code:
            raise ValueError(
                f"target_entity_code({self.target_entity_code})とpeer_entity_code({self.peer_entity_code})が"
                "同一です(Self-Peer Exclusion Guard違反、fail closed)"
            )
        if self.target_observation.entity_code != self.target_entity_code:
            raise ValueError("target_observation.entity_codeがtarget_entity_codeと一致しません")
        if self.peer_observation.entity_code != self.peer_entity_code:
            raise ValueError("peer_observation.entity_codeがpeer_entity_codeと一致しません")
        if self.target_observation.metric_type != self.metric_type or self.peer_observation.metric_type != self.metric_type:
            raise ValueError("target_observation/peer_observationのmetric_typeがmetric_typeと一致しません")
        if self.target_observation.as_of != self.comparison_as_of or self.peer_observation.as_of != self.comparison_as_of:
            raise ValueError(
                "target_observation/peer_observationのas_ofがcomparison_as_ofと一致しません(Same-As-Of Rule違反、要件v1 §10)"
            )
        both_available = (
            self.target_observation.availability == PeerMetricAvailability.AVAILABLE
            and self.peer_observation.availability == PeerMetricAvailability.AVAILABLE
        )
        if not self.exclusion_reasons:
            # Comparable(排除理由なし)なら、両Observationが必ずAVAILABLEで、differenceも
            # 必ず計算されている必要がある(Silent Incomparable禁止、Defense-in-depth)。
            if not both_available:
                raise ValueError(
                    "exclusion_reasonsが空(Comparable)ですが、target_observation/peer_observationの"
                    "少なくとも一方がAVAILABLEではありません(契約違反、fail closed)"
                )
            if self.difference is None:
                raise ValueError("exclusion_reasonsが空(Comparable)ですがdifferenceが計算されていません(fail closed)")
            expected = self.target_observation.value - self.peer_observation.value  # type: ignore[operator]
            if self.difference != expected:
                raise ValueError(f"difference({self.difference})がtarget-peer({expected})と一致しません")
        elif self.difference is not None:
            raise ValueError(
                "exclusion_reasonsが非空(Incomparable)の場合、differenceは設定できません(fail closed、値を捏造しない)"
            )


@dataclass(kw_only=True, frozen=True)
class PeerAggregateContext:
    """複数AcceptedPeerを集約したContext(要件v1 §13)。

    `lib.valuation.historical_context_builder`と同じ統計定義(Empirical
    CDF Percentile、Ordered Midpoint Median、外部Statistics Library
    非依存)をそのまま再利用する(要件v1 §6の「既存Infrastructureの
    再利用」原則、統計定義を独自に再定義しない)。Interpretationは
    一切含まない(「割安/割高」等の語はこのModuleのどこにも出現しない)。
    """

    target_entity_code: str
    metric_type: PeerMetricType
    as_of: datetime
    selection_version: str = SELECTION_VERSION_V1

    target_value: Decimal
    target_observation_evidence_id: str
    peer_count: int
    minimum_sample_count: int
    included_peer_entity_codes: tuple[str, ...]
    included_peer_observation_evidence_ids: tuple[str, ...]

    peer_min: Decimal
    peer_median: Decimal
    peer_max: Decimal
    median_method: str

    target_percentile: Decimal
    percentile_method: str
    percentile_scale: str

    excluded_peer_entity_codes: tuple[str, ...] = field(default_factory=tuple)

    available_at: datetime

    def __post_init__(self) -> None:
        if self.as_of.tzinfo is None:
            raise ValueError("as_of はtz-awareである必要があります")
        if self.available_at.tzinfo is None:
            raise ValueError("available_at はtz-awareである必要があります")
        if self.available_at > self.as_of:
            raise ValueError(
                f"available_at({self.available_at.isoformat()})がas_of({self.as_of.isoformat()})より後です(fail closed)"
            )
        if self.peer_count != len(self.included_peer_entity_codes):
            raise ValueError(
                f"peer_count({self.peer_count})がincluded_peer_entity_codesの件数"
                f"({len(self.included_peer_entity_codes)})と一致しません"
            )
        if len(set(self.included_peer_entity_codes)) != len(self.included_peer_entity_codes):
            raise ValueError("included_peer_entity_codesに重複があります(Duplicate Parent Guard)")
        if self.target_entity_code in self.included_peer_entity_codes:
            raise ValueError(
                f"target_entity_code({self.target_entity_code})がincluded_peer_entity_codesへ混入しています"
                "(Self-Peer Exclusion Guard違反)"
            )
        if len(self.included_peer_observation_evidence_ids) != len(self.included_peer_entity_codes):
            raise ValueError(
                f"included_peer_observation_evidence_idsの件数({len(self.included_peer_observation_evidence_ids)})が"
                f"included_peer_entity_codesの件数({len(self.included_peer_entity_codes)})と一致しません"
                "(Dangling Parent Guard)"
            )
        if len(set(self.included_peer_observation_evidence_ids)) != len(self.included_peer_observation_evidence_ids):
            raise ValueError("included_peer_observation_evidence_idsに重複があります(Duplicate Parent Guard)")
        if self.target_observation_evidence_id in self.included_peer_observation_evidence_ids:
            raise ValueError(
                f"target_observation_evidence_id({self.target_observation_evidence_id})が"
                "included_peer_observation_evidence_idsへ混入しています(Current Observation Contamination Guard)"
            )
        if self.peer_count < self.minimum_sample_count:
            raise ValueError(
                f"peer_count({self.peer_count})がminimum_sample_count({self.minimum_sample_count})未満です"
                "(Sample Sufficiency Policy違反、この状態のRecordは生成禁止、Builderは代わりにNoneを返す)"
            )
        if not (self.peer_min <= self.peer_median <= self.peer_max):
            raise ValueError(
                f"peer_min({self.peer_min}) <= peer_median({self.peer_median}) <= peer_max({self.peer_max})が成立しません"
            )
        if not (Decimal(0) <= self.target_percentile <= Decimal(100)):
            raise ValueError(f"target_percentile({self.target_percentile})が[0, 100]の範囲外です")


__all__ = [
    "CLASSIFICATION_SYSTEM_TSE_SECTOR_33",
    "MINIMUM_PEER_SAMPLE_COUNT",
    "SELECTION_METHOD_SAME_TSE_SECTOR_33_CODE",
    "SELECTION_VERSION_V1",
    "STALE_FISCAL_CYCLE_THRESHOLD",
    "AcceptedPeer",
    "ExcludedPeerCandidate",
    "PeerAggregateContext",
    "PeerCandidate",
    "PeerComparisonRecord",
    "PeerEntityComparabilityResult",
    "PeerExclusionReason",
    "PeerMetricAvailability",
    "PeerMetricObservation",
    "PeerMetricType",
    "PeerUniverseSnapshot",
]
