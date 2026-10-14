"""Peer Metric Observation / Comparison / Aggregate Contextの構築(Stage
3.17、D0095)。

**新しいValuation計算Logicは作らない(要件v1 §9/§18)**: `LatestReported
FyPerRecord`/`CurrentFyCompanyForecastPerRecord`とそれらのEvidence化
(`lib.valuation.evidence`)は既存Production Builder(`lib.valuation.
builder.build_latest_reported_fy_per()`/`lib.valuation.current_fy_
forecast_builder.build_current_fy_company_forecast_per()`)を呼び出し側
がそのまま使い、この関数群は「既に構築済みのRecord + Evidence」を
`PeerMetricObservation`へ変換するだけの薄いAdapterである(Target/Peerの
区別なく、Entity非依存のこれら既存Builderをそのまま流用できる、要件
v1 §18「新しいProvider Architectureを作らない」)。

Percentile/Medianの統計定義は`lib.valuation.model`(Historical Valuation
Contextと同じEmpirical CDF Percentile・Ordered Midpoint Median)を再利用
する——独自の統計定義を作らない(要件v1 §6)。
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

from lib.evidence.model import EvidenceRecord
from lib.peer.comparability import evaluate_peer_metric_comparability
from lib.peer.evidence import verify_observation_parent_identity
from lib.peer.model import (
    MINIMUM_PEER_SAMPLE_COUNT,
    SELECTION_VERSION_V1,
    AcceptedPeer,
    PeerAggregateContext,
    PeerComparisonRecord,
    PeerMetricAvailability,
    PeerMetricObservation,
    PeerMetricType,
)
from lib.valuation.evidence import current_fy_company_forecast_per_to_evidence, latest_reported_fy_per_evidence_id_v2
from lib.valuation.model import (
    MEDIAN_METHOD_ORDERED_MIDPOINT,
    PERCENTILE_METHOD_EMPIRICAL_CDF_LE,
    PERCENTILE_SCALE_PERCENT_0_100,
    CurrentFyCompanyForecastPerRecord,
    LatestReportedFyPerRecord,
)


def latest_reported_fy_per_record_to_peer_observation(
    record: LatestReportedFyPerRecord, *, evidence: EvidenceRecord, as_of: datetime
) -> PeerMetricObservation:
    """`LatestReportedFyPerRecord`(D0077、既存Production Builder出力)を
    `PeerMetricObservation`へ変換する。`evidence`は呼び出し側が既存
    `lib.valuation.evidence.latest_reported_fy_per_to_evidence_v2()`で
    構築済みのものを渡す(このAdapter自身はEvidence ID採番Logicを持たない、
    二重実装しない)。

    **Semantic Identity検証(Stage 3.17.1、D0096 Finding 5)**: `evidence`
    が本当に`record`から構築されたものかを、`related_codes`一致だけでなく
    (1)`lib.valuation.evidence.latest_reported_fy_per_evidence_id_v2()`
    から導出される期待Evidence IDとの完全一致、(2)`verify_observation_
    parent_identity()`によるMetric Family(`is_latest_reported_fy_per_
    v2_evidence()`)・FACT/DERIVED/VALUATION・PIT検証、(3)`value_date`と
    `record.price_date`の一致で検証する。これにより、`CURRENT_FY_
    COMPANY_FORECAST_PER`Evidence等、意味的に誤ったParentが渡されても
    fail closedで拒否する。
    """
    expected_evidence_id = latest_reported_fy_per_evidence_id_v2(record)
    problems: list[str] = []
    if evidence.evidence_id != expected_evidence_id:
        problems.append(f"evidence_id={evidence.evidence_id}が期待Evidence ID({expected_evidence_id})と一致しません")
    if evidence.related_codes != (record.entity_code,):
        problems.append(f"related_codes={evidence.related_codes}がrecord.entity_code({record.entity_code})と一致しません")
    if evidence.value_date != record.price_date:
        problems.append(f"value_date={evidence.value_date}がrecord.price_date({record.price_date})と一致しません")
    if problems:
        raise ValueError(f"evidence(evidence_id={evidence.evidence_id})がrecordに対応していません: {'; '.join(problems)}")
    verify_observation_parent_identity(
        evidence, entity_code=record.entity_code, metric_type=PeerMetricType.LATEST_REPORTED_FY_PER, as_of_ceiling=as_of
    )
    return PeerMetricObservation(
        entity_code=record.entity_code,
        metric_type=PeerMetricType.LATEST_REPORTED_FY_PER,
        as_of=as_of,
        availability=PeerMetricAvailability.AVAILABLE,
        value=record.multiple,
        value_available_at=evidence.source.available_at,
        fiscal_period_end=record.fiscal_period_end,
        accounting_standard=record.accounting_standard,
        source_evidence_id=evidence.evidence_id,
    )


def current_fy_company_forecast_per_record_to_peer_observation(
    record: CurrentFyCompanyForecastPerRecord, *, evidence: EvidenceRecord, as_of: datetime
) -> PeerMetricObservation:
    """`CurrentFyCompanyForecastPerRecord`(D0084、既存Production Builder
    出力)を`PeerMetricObservation`へ変換する。`forecast_period_end`を
    `fiscal_period_end`相当としてComparability Guard(`lib.peer.
    comparability.evaluate_peer_metric_comparability()`)へ渡す。

    **Exact Record/Evidence Canonical Identity検証(Stage 3.17.2、D0097
    Finding 5)**: この Metric Familyには`lib.valuation.evidence`に
    公開Canonical Evidence ID Helper(`latest_reported_fy_per_evidence_
    id_v2()`相当)が存在しない(Stage 3.15 Frozen、新設しない)。D0096の
    Check(`related_codes`/`value_date`一致、`verify_observation_parent_
    identity()`)だけでは、**同一Entity・同一Price Date・同一Metric
    Family**だが**異なる`source_version_id`(=異なるDisclosure、異なる
    FEPS)**を持つ別RecordのEvidenceが誤って受理されてしまう欠陥が残って
    いた(D0096 Codex Re-Audit Finding 5、`forecast_wrong_record_
    accepted`)。

    独自のEvidence Identity Algorithmを新設せず、`evidence`自身が申告する
    `source_authority_class`/`originating_source`/`delivery_provider`を
    使って、既存Production Builder`current_fy_company_forecast_per_to_
    evidence()`を`record`から**実際に呼び出し**、その結果(Canonical
    Expected Evidence)と`evidence`の`evidence_id`/`source.source_id`/
    `source.available_at`を比較する。`source.source_id`には`record.
    source_version_id`が含まれる(既存Production Builderの既存Format、
    ここでは再現していない)ため、`source_version_id`が異なるRecordの
    Evidenceは必ず不一致になりfail closedする。
    """
    if evidence.source.originating_source is None or evidence.source.delivery_provider is None:
        raise ValueError(
            f"evidence(evidence_id={evidence.evidence_id})のoriginating_source/delivery_providerがNoneのため、"
            "Canonical Evidenceを再構築できません(fail closed)"
        )
    expected_evidence = current_fy_company_forecast_per_to_evidence(
        record,
        source_authority_class=evidence.source.source_authority_class,
        originating_source=evidence.source.originating_source,
        delivery_provider=evidence.source.delivery_provider,
    )
    problems: list[str] = []
    if evidence.evidence_id != expected_evidence.evidence_id:
        problems.append(f"evidence_id={evidence.evidence_id}が期待Evidence ID({expected_evidence.evidence_id})と一致しません")
    if evidence.source.source_id != expected_evidence.source.source_id:
        problems.append(
            f"source.source_id={evidence.source.source_id}が期待source_id({expected_evidence.source.source_id})と"
            "一致しません(source_version_id不一致の可能性)"
        )
    if evidence.source.available_at != expected_evidence.source.available_at:
        problems.append(
            f"source.available_at={evidence.source.available_at.isoformat()}が期待値"
            f"({expected_evidence.source.available_at.isoformat()})と一致しません"
        )
    if evidence.related_codes != (record.entity_code,):
        problems.append(f"related_codes={evidence.related_codes}がrecord.entity_code({record.entity_code})と一致しません")
    if evidence.value_date != record.price_date:
        problems.append(f"value_date={evidence.value_date}がrecord.price_date({record.price_date})と一致しません")
    if problems:
        raise ValueError(f"evidence(evidence_id={evidence.evidence_id})がrecordに対応していません: {'; '.join(problems)}")
    verify_observation_parent_identity(
        evidence,
        entity_code=record.entity_code,
        metric_type=PeerMetricType.CURRENT_FY_COMPANY_FORECAST_PER,
        as_of_ceiling=as_of,
    )
    return PeerMetricObservation(
        entity_code=record.entity_code,
        metric_type=PeerMetricType.CURRENT_FY_COMPANY_FORECAST_PER,
        as_of=as_of,
        availability=PeerMetricAvailability.AVAILABLE,
        value=record.multiple,
        value_available_at=evidence.source.available_at,
        fiscal_period_end=record.forecast_period_end,
        accounting_standard=record.accounting_standard,
        source_evidence_id=evidence.evidence_id,
    )


def missing_peer_metric_observation(
    *,
    entity_code: str,
    metric_type: PeerMetricType,
    as_of: datetime,
    availability: PeerMetricAvailability = PeerMetricAvailability.MISSING,
    note: str = "",
) -> PeerMetricObservation:
    """値が存在しないPeer Metric Observationを明示的に構築する(要件v1
    §11「Missingを0にしない」)。`availability=AVAILABLE`はここでは
    受け付けない(値付きの構築は上記2つの変換関数を使う、fail closed)。
    """
    if availability == PeerMetricAvailability.AVAILABLE:
        raise ValueError(
            "missing_peer_metric_observation()はAVAILABLE以外のavailabilityのみ受け付けます"
            "(値付きObservationはlatest_reported_fy_per_record_to_peer_observation()等を使ってください)"
        )
    return PeerMetricObservation(
        entity_code=entity_code, metric_type=metric_type, as_of=as_of, availability=availability, note=note
    )


def build_peer_comparison_record(
    *,
    target_entity_code: str,
    accepted_peer: AcceptedPeer,
    metric_type: PeerMetricType,
    comparison_as_of: datetime,
    target_observation: PeerMetricObservation,
    peer_observation: PeerMetricObservation,
) -> PeerComparisonRecord:
    """1 Target × 1 Peer × 1 MetricのComparisonを、Comparability Guardを
    適用した上で構築する(要件v1 §10 Same-As-Of Rule + §12 Comparison
    Record)。Interpretationは一切含まない(単なる数値の差分のみ)。

    **AcceptedPeer必須(Stage 3.17.1、D0096 Finding 1)**: 以前は生の
    `peer_entity_code: str`を直接受け取れたため、`PeerCandidate` →
    `evaluate_peer_entity_eligibility()` → `AcceptedPeer` → Comparison
    というContractをProduction API自体が強制していなかった(Eligibility
    Bypass、D0095 Codex Finding 1)。`accepted_peer`を必須Inputにし、
    以下をfail closedで再検証することで、通常のProduction Comparison
    PathがAcceptedPeer無しには進めないようにする(Test Fixture内で
    `AcceptedPeer`を直接構築すること自体は許容、Production APIに
    Bypass Pathを残さないことが目的):

    - `accepted_peer.entity_code == peer_observation.entity_code`
    - `accepted_peer.as_of == comparison_as_of`
    - `target_observation.entity_code == target_entity_code`
    - `target_observation.as_of == comparison_as_of`
    - `peer_observation.as_of == comparison_as_of`
    """
    if accepted_peer.entity_code != peer_observation.entity_code:
        raise ValueError(
            f"accepted_peer.entity_code({accepted_peer.entity_code})がpeer_observation.entity_code"
            f"({peer_observation.entity_code})と一致しません(fail closed、Eligibility Bypass防止)"
        )
    if accepted_peer.as_of != comparison_as_of:
        raise ValueError(
            f"accepted_peer.as_of({accepted_peer.as_of.isoformat()})がcomparison_as_of"
            f"({comparison_as_of.isoformat()})と一致しません(fail closed)"
        )
    if target_observation.entity_code != target_entity_code:
        raise ValueError(
            f"target_observation.entity_code({target_observation.entity_code})がtarget_entity_code"
            f"({target_entity_code})と一致しません(fail closed)"
        )
    if target_observation.as_of != comparison_as_of:
        raise ValueError(
            f"target_observation.as_of({target_observation.as_of.isoformat()})がcomparison_as_of"
            f"({comparison_as_of.isoformat()})と一致しません(Same-As-Of Rule違反、fail closed)"
        )
    if peer_observation.as_of != comparison_as_of:
        raise ValueError(
            f"peer_observation.as_of({peer_observation.as_of.isoformat()})がcomparison_as_of"
            f"({comparison_as_of.isoformat()})と一致しません(Same-As-Of Rule違反、fail closed)"
        )

    peer_entity_code = accepted_peer.entity_code
    reasons = evaluate_peer_metric_comparability(
        metric_type, target_observation=target_observation, peer_observation=peer_observation
    )
    difference: Decimal | None = None
    if not reasons:
        target_value = target_observation.value
        peer_value = peer_observation.value
        if target_value is None or peer_value is None:
            # evaluate_peer_metric_comparability()の契約上、reasonsが空ならtarget/peer
            # 双方がAVAILABLE(=value非None)のはず(Defense-in-depth、通常到達しない)。
            raise ValueError(
                f"target_entity_code={target_entity_code}, peer_entity_code={peer_entity_code}: "
                "Comparability Guard通過後にvalueがNoneです(契約違反、fail closed)"
            )
        difference = target_value - peer_value
    return PeerComparisonRecord(
        target_entity_code=target_entity_code,
        peer_entity_code=peer_entity_code,
        metric_type=metric_type,
        comparison_as_of=comparison_as_of,
        target_observation=target_observation,
        peer_observation=peer_observation,
        exclusion_reasons=reasons,
        difference=difference,
    )


def _ordered_midpoint_median(sorted_values: Sequence[Decimal]) -> Decimal:
    """`lib.valuation.historical_context_builder._ordered_midpoint_median()`
    と同じ定義(奇数nは中央値そのもの、偶数nは中央2値のDecimal平均)。
    元関数はPrivate Helperのため直接Importせず、同一の単純な定義をこの
    Moduleへも保持する(`MEDIAN_METHOD_ORDERED_MIDPOINT`という共通の定義名
    Constantは`lib.valuation.model`から再利用し、計算式自体の意味が
    Silentに変わらないようにする)。
    """
    n = len(sorted_values)
    if n == 0:
        raise ValueError("空のSequenceのMedianは計算できません")
    mid = n // 2
    if n % 2 == 1:
        return sorted_values[mid]
    return (sorted_values[mid - 1] + sorted_values[mid]) / Decimal(2)


def build_peer_aggregate_context(
    *,
    target_entity_code: str,
    metric_type: PeerMetricType,
    as_of: datetime,
    target_observation: PeerMetricObservation,
    comparison_records: Sequence[PeerComparisonRecord],
    minimum_sample_count: int = MINIMUM_PEER_SAMPLE_COUNT,
    selection_version: str = SELECTION_VERSION_V1,
) -> PeerAggregateContext | None:
    """複数`PeerComparisonRecord`からAggregate Contextをfail closedで構築
    する(要件v1 §13)。

    **`None`の意味(Silent Excludeではなく、値が無いことの明示)**:
    - `target_observation.availability != AVAILABLE`(Targetの値自体が
      無ければ、そもそもPercentileを計算できない)。
    - Comparable(`exclusion_reasons`が空)なPeer Comparisonの件数が
      `minimum_sample_count`未満(Sample Sufficiency Policy)。

    `selection_version`は呼び出し側が使った`lib.peer.universe.resolve_
    peer_candidate_universe()`のPeer Universe Selection Versionをそのまま
    渡す(要件v1 §6、Context Evidence Identityへ反映するため、`lib.peer.
    evidence`参照)。

    Interpretation(割安/割高等)は一切含まない、記述統計のみ。
    """
    if as_of.tzinfo is None:
        raise ValueError("as_of はtz-awareである必要があります")
    if target_observation.entity_code != target_entity_code:
        raise ValueError("target_observation.entity_codeがtarget_entity_codeと一致しません")
    if target_observation.metric_type != metric_type:
        raise ValueError("target_observation.metric_typeがmetric_typeと一致しません")
    if target_observation.as_of != as_of:
        raise ValueError("target_observation.as_ofがas_ofと一致しません(Same-As-Of Rule違反)")

    mismatched = [
        r
        for r in comparison_records
        if r.target_entity_code != target_entity_code or r.metric_type != metric_type or r.comparison_as_of != as_of
    ]
    if mismatched:
        raise ValueError(
            f"comparison_recordsにtarget_entity_code/metric_type/comparison_as_ofが一致しないRecordが"
            f"{len(mismatched)}件含まれています(fail closed)"
        )

    if target_observation.availability != PeerMetricAvailability.AVAILABLE or target_observation.value is None:
        return None

    included = [r for r in comparison_records if not r.exclusion_reasons]
    excluded_codes = tuple(sorted({r.peer_entity_code for r in comparison_records if r.exclusion_reasons}))
    peer_count = len(included)
    if peer_count < minimum_sample_count:
        return None

    value_by_entity: dict[str, Decimal] = {}
    evidence_id_by_entity: dict[str, str] = {}
    available_at_by_entity: dict[str, datetime] = {}
    for r in included:
        peer_value = r.peer_observation.value
        peer_evidence_id = r.peer_observation.source_evidence_id
        peer_available_at = r.peer_observation.value_available_at
        if peer_value is None or peer_evidence_id is None or peer_available_at is None:
            # PeerComparisonRecord.__post_init__のContract上、exclusion_reasonsが空なら
            # peer_observation.value/source_evidence_id/value_available_atは非Noneのはず
            # (Defense-in-depth、通常到達しない)。
            raise ValueError(
                f"peer_entity_code={r.peer_entity_code}: Comparable判定後にvalue/source_evidence_id/"
                "value_available_atがNoneです(契約違反)"
            )
        value_by_entity[r.peer_entity_code] = peer_value
        evidence_id_by_entity[r.peer_entity_code] = peer_evidence_id
        available_at_by_entity[r.peer_entity_code] = peer_available_at

    included_peer_entity_codes = tuple(sorted(value_by_entity))
    included_peer_observation_evidence_ids = tuple(evidence_id_by_entity[code] for code in included_peer_entity_codes)

    peer_values = sorted(value_by_entity[code] for code in included_peer_entity_codes)
    peer_min = peer_values[0]
    peer_max = peer_values[-1]
    peer_median = _ordered_midpoint_median(peer_values)

    target_value = target_observation.value
    if target_observation.source_evidence_id is None:
        raise ValueError(f"target_entity_code={target_entity_code}: target_observation.source_evidence_idがNoneです(契約違反)")
    target_observation_evidence_id = target_observation.source_evidence_id
    count_le = sum(1 for v in peer_values if v <= target_value)
    target_percentile = Decimal(count_le) * Decimal(100) / Decimal(peer_count)

    all_available_at = [
        target_observation.value_available_at,
        *(available_at_by_entity[code] for code in included_peer_entity_codes),
    ]
    non_null_available_at = [a for a in all_available_at if a is not None]
    available_at = max(non_null_available_at)

    return PeerAggregateContext(
        target_entity_code=target_entity_code,
        metric_type=metric_type,
        as_of=as_of,
        selection_version=selection_version,
        target_value=target_value,
        target_observation_evidence_id=target_observation_evidence_id,
        peer_count=peer_count,
        minimum_sample_count=minimum_sample_count,
        included_peer_entity_codes=included_peer_entity_codes,
        included_peer_observation_evidence_ids=included_peer_observation_evidence_ids,
        peer_min=peer_min,
        peer_median=peer_median,
        peer_max=peer_max,
        median_method=MEDIAN_METHOD_ORDERED_MIDPOINT,
        target_percentile=target_percentile,
        percentile_method=PERCENTILE_METHOD_EMPIRICAL_CDF_LE,
        percentile_scale=PERCENTILE_SCALE_PERCENT_0_100,
        excluded_peer_entity_codes=excluded_codes,
        available_at=available_at,
    )


__all__ = [
    "build_peer_aggregate_context",
    "build_peer_comparison_record",
    "current_fy_company_forecast_per_record_to_peer_observation",
    "latest_reported_fy_per_record_to_peer_observation",
    "missing_peer_metric_observation",
]
