"""LATEST_REPORTED_FY_PER_HISTORICAL_CONTEXTの選定・計算(Stage 3.15/3.15.1、
D0089/D0090)。

D0087(7203 Multi-Year Price Snapshot)+ D0088(Historical Sample PIT
Correction Scratch)で確認した「Historical PER Monthly Anchors分布」を、
Production Codeとして再現可能・PIT-safeに構築する。既存`lib.valuation.
builder.build_latest_reported_fy_per()`(D0077)をそのまま再利用し、
Anchor選定(どのas_ofについてPERを計算するか)・Price/EPS取得は一切
再実装しない——この関数が受け取るのは、呼び出し側が既に`build_latest_
reported_fy_per()`で構築済みの`LatestReportedFyPerRecord`群(Historical
Anchors + Current Reference)そのものである。

**責務分担(D0077 builder.pyと同じ設計思想)**: Anchor生成(どの月を
「完了した暦月」とみなすか、`lib.market_calendar.TradingCalendar.
completed_month_end_sessions()`)・EPS/Price取得・Corporate Action Guard
起因のExclusion集計は呼び出し側(Orchestration)の責務。この関数は
「既に選定済みのHistorical/Current PER Recordの集合が、Historical
Context Factとして安全に集約できるか」をDefense-in-depthで再検証し、
記述統計(min/median/max/percentile/distance)をDecimal専用・外部
Statistics Library非依存で計算する。

**PIT Defense-in-depth(要件v1 §7)**: `historical_records`の中に
`as_of > current_reference_as_of`のRecordが1件でもあれば、Silent Exclude
せず`LookAheadBiasError`で即座に失敗する。呼び出し側のAnchor生成
(Orchestration側、通常は`TradingCalendar.completed_month_end_sessions()`
が構造的にCurrent Referenceと同一暦月以降を生成しない)に不具合があっても、
この層で必ず食い止める。

**Stage 3.15.1(D0090)Hardening**: (1) 単純な`as_of > current_reference_
as_of`比較だけでは、Current Referenceと同一暦月内でtimestampがReference
より前のHistorical Observationを見逃すため、同一`(year, month)`のRecordも
`LookAheadBiasError`でReject(同一暦月ガード)。(2) Historical/Current
Observation IDは`lib.valuation.evidence.latest_reported_fy_per_evidence_
id_v2()`(entity_code + price_date + source_version_id、Collision-Safe
Identity)を使う——既存v1 ID(entity_code + price_dateのみ)はSilentに
意味変更していない。
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

from lib.errors import LookAheadBiasError
from lib.evidence.model import Frequency
from lib.valuation.evidence import latest_reported_fy_per_available_at, latest_reported_fy_per_evidence_id_v2
from lib.valuation.model import (
    MEDIAN_METHOD_ORDERED_MIDPOINT,
    MINIMUM_MONTHLY_OBSERVATIONS,
    PERCENTILE_METHOD_EMPIRICAL_CDF_LE,
    PERCENTILE_SCALE_PERCENT_0_100,
    DenominatorRegimeSummary,
    HistoricalContextStatus,
    LatestReportedFyPerHistoricalContextRecord,
    LatestReportedFyPerRecord,
)


def _ordered_midpoint_median(sorted_values: Sequence[Decimal]) -> Decimal:
    """`MEDIAN_METHOD_ORDERED_MIDPOINT`(要件v1 §11): 昇順ソート済みの値から、
    奇数nは中央値そのもの、偶数nは中央2値のDecimal平均を返す。外部Statistics
    Libraryの暗黙挙動には依存しない。"""
    n = len(sorted_values)
    if n == 0:
        raise ValueError("空のSequenceのMedianは計算できません")
    mid = n // 2
    if n % 2 == 1:
        return sorted_values[mid]
    return (sorted_values[mid - 1] + sorted_values[mid]) / Decimal(2)


def build_latest_reported_fy_per_historical_context(
    *,
    entity_code: str,
    current_reference_as_of: datetime,
    current_record: LatestReportedFyPerRecord,
    historical_records: Sequence[LatestReportedFyPerRecord],
    attempted_anchor_count: int,
    excluded_future_anchor_count: int,
    unavailable_denominator_count: int,
    corporate_action_excluded_count: int,
    minimum_sample_count: int = MINIMUM_MONTHLY_OBSERVATIONS,
) -> LatestReportedFyPerHistoricalContextRecord | None:
    """LATEST_REPORTED_FY_PER_HISTORICAL_CONTEXTをfail closedで構築する(要件v1)。

    **`None`の意味(Silent Excludeではなく、値が無いことの明示)**:
    - `len(historical_records) < minimum_sample_count`(Sample Sufficiency
      Policy、要件v1 §13。n=0とn=1..11のいずれも同じ扱い。呼び出し側は
      `len(historical_records)`を別途保持しているため、DataGap記述の際に
      MISSINGとサンプル不足を区別できる)。

    **例外を送出する場合(入力そのものが契約に反する場合)**:
    - `current_record.entity_code`/各`historical_records[i].entity_code`が
      `entity_code`と一致しない(`ValueError`)。
    - `current_record.as_of != current_reference_as_of`(`ValueError`、
      「Current Reference」の定義そのものの不一致)。
    - `historical_records`の中に`as_of > current_reference_as_of`のRecordが
      1件でもある(`LookAheadBiasError`、要件v1 §7、Silent Exclude禁止)。
    - Historical Observation IDに重複がある、またはCurrent Observation ID
      がHistorical Observation IDsへ混入している(`ValueError`、要件v1 §7/
      §19、Dangling/Duplicate/Contamination Parent Guard)。
    - 同一`fiscal_period_end`のDenominator Regime内でEPS値/source_version_id
      が一致しない(`ValueError`、Regime構成の推測を禁止)。
    - `attempted_anchor_count`が内訳(`excluded_future_anchor_count` +
      `unavailable_denominator_count` + `corporate_action_excluded_count` +
      `len(historical_records)`)と一致しない(`ValueError`、呼び出し側の
      Bookkeepingを再検証、Defense-in-depth)。
    - 合成`available_at`が`current_reference_as_of`より後になる
      (`ValueError`、構造上通常発生しないが最終防衛としてfail closed)。
    """
    if current_reference_as_of.tzinfo is None:
        raise ValueError("current_reference_as_of はtz-awareである必要があります")

    if current_record.entity_code != entity_code:
        raise ValueError(f"current_record.entity_code({current_record.entity_code})がentity_code({entity_code})と一致しません")
    mismatched_entity = [h for h in historical_records if h.entity_code != entity_code]
    if mismatched_entity:
        raise ValueError(
            f"historical_recordsにentity_code({entity_code})と一致しないRecordが含まれています: "
            f"{sorted({h.entity_code for h in mismatched_entity})}"
        )
    if current_record.as_of != current_reference_as_of:
        raise ValueError(
            f"current_record.as_of({current_record.as_of.isoformat()})がcurrent_reference_as_of"
            f"({current_reference_as_of.isoformat()})と一致しません(Current Referenceの定義不一致)"
        )

    future_anchors = [h for h in historical_records if h.as_of > current_reference_as_of]
    if future_anchors:
        offending = sorted(f"{h.entity_code}@{h.as_of.isoformat()}" for h in future_anchors)
        raise LookAheadBiasError(
            f"current_reference_as_of({current_reference_as_of.isoformat()})より後のas_ofを持つ"
            f"Historical PER Observationが{len(future_anchors)}件含まれています(Silent Exclude禁止、"
            f"fail closed): {offending}"
        )

    # Stage 3.15.1(D0090)Hardening: 単純な`as_of > current_reference_as_of`比較だけでは、
    # Current Referenceと同一暦月内でtimestampがReferenceより前のHistorical Observation
    # (例: Current Referenceが2024-11-15、Historical Anchorが2024-11-01)を見逃す——
    # その月自体はまだ完了しておらず、Historical Sampleへ含めるべきではない
    # (`lib.market_calendar.TradingCalendar.completed_month_end_sessions()`が
    # Orchestration側でCurrent Referenceと同一暦月を構造的に除外しているのと同じ原則を、
    # Builder側でもDefense-in-depthとして再検証する)。
    current_reference_month = (current_reference_as_of.year, current_reference_as_of.month)
    same_month_anchors = [h for h in historical_records if (h.as_of.year, h.as_of.month) == current_reference_month]
    if same_month_anchors:
        offending_same_month = sorted(f"{h.entity_code}@{h.as_of.isoformat()}" for h in same_month_anchors)
        raise LookAheadBiasError(
            f"current_reference_as_of({current_reference_as_of.isoformat()})と同一暦月"
            f"({current_reference_month[0]}-{current_reference_month[1]:02d})のHistorical PER "
            f"Observationが{len(same_month_anchors)}件含まれています(timestampがReferenceより前でも、"
            f"その月自体が未完了のためReject、fail closed): {offending_same_month}"
        )

    current_per_observation_id = latest_reported_fy_per_evidence_id_v2(current_record)
    historical_observation_ids = tuple(latest_reported_fy_per_evidence_id_v2(h) for h in historical_records)
    if len(set(historical_observation_ids)) != len(historical_observation_ids):
        duplicates = sorted({oid for oid in historical_observation_ids if historical_observation_ids.count(oid) > 1})
        raise ValueError(f"historical_observation_idsに重複があります(Duplicate Parent Guard): {duplicates}")
    if current_per_observation_id in historical_observation_ids:
        raise ValueError(
            f"current_per_observation_id({current_per_observation_id})がhistorical_observation_idsへ"
            "混入しています(Current Observation Contamination Guard)"
        )

    sample_count = len(historical_records)
    counted_total = excluded_future_anchor_count + unavailable_denominator_count + corporate_action_excluded_count + sample_count
    if attempted_anchor_count != counted_total:
        raise ValueError(
            f"attempted_anchor_count({attempted_anchor_count})が内訳の合計({counted_total} = "
            f"excluded_future_anchor_count({excluded_future_anchor_count}) + "
            f"unavailable_denominator_count({unavailable_denominator_count}) + "
            f"corporate_action_excluded_count({corporate_action_excluded_count}) + "
            f"sample_count({sample_count}))と一致しません(呼び出し側のBookkeeping不整合)"
        )

    if sample_count < minimum_sample_count:
        return None

    regimes_by_fpe: dict = {}
    for h in historical_records:
        existing = regimes_by_fpe.get(h.fiscal_period_end)
        if existing is None:
            regimes_by_fpe[h.fiscal_period_end] = {
                "eps_value": h.eps_value,
                "source_version_id": h.source_version_id,
                "count": 1,
            }
            continue
        if existing["eps_value"] != h.eps_value or existing["source_version_id"] != h.source_version_id:
            raise ValueError(
                f"fiscal_period_end={h.fiscal_period_end.isoformat()}のDenominator Regime内でEPS値/"
                "source_version_idが一致しません(推測でRegimeを統合しない、fail closed): "
                f"({existing['eps_value']}, {existing['source_version_id']}) != ({h.eps_value}, {h.source_version_id})"
            )
        existing["count"] += 1

    denominator_regimes = tuple(
        DenominatorRegimeSummary(
            fiscal_period_end=fpe,
            eps_value=info["eps_value"],
            source_version_id=info["source_version_id"],
            observation_count=info["count"],
        )
        for fpe, info in sorted(regimes_by_fpe.items())
    )

    sorted_pers = sorted(h.multiple for h in historical_records)
    historical_min = sorted_pers[0]
    historical_max = sorted_pers[-1]
    historical_median = _ordered_midpoint_median(sorted_pers)

    current_per = current_record.multiple
    count_le = sum(1 for p in sorted_pers if p <= current_per)
    current_percentile = Decimal(count_le) * Decimal(100) / Decimal(sample_count)
    current_minus_historical_median = current_per - historical_median

    sample_as_of_values = [h.as_of for h in historical_records]
    historical_sample_start_as_of = min(sample_as_of_values)
    historical_sample_end_as_of = max(sample_as_of_values)

    all_available_at = [latest_reported_fy_per_available_at(h) for h in historical_records]
    all_available_at.append(latest_reported_fy_per_available_at(current_record))
    available_at = max(all_available_at)
    if available_at > current_reference_as_of:
        raise ValueError(
            f"合成available_at({available_at.isoformat()})がcurrent_reference_as_of"
            f"({current_reference_as_of.isoformat()})より後です(fail closed)"
        )

    return LatestReportedFyPerHistoricalContextRecord(
        entity_code=entity_code,
        as_of=current_reference_as_of,
        historical_sample_start_as_of=historical_sample_start_as_of,
        historical_sample_end_as_of=historical_sample_end_as_of,
        anchor_frequency=Frequency.MONTHLY,
        sample_count=sample_count,
        minimum_sample_count=minimum_sample_count,
        historical_observation_ids=historical_observation_ids,
        denominator_regimes=denominator_regimes,
        distinct_denominator_regime_count=len(denominator_regimes),
        historical_min=historical_min,
        historical_median=historical_median,
        historical_max=historical_max,
        median_method=MEDIAN_METHOD_ORDERED_MIDPOINT,
        current_reference_as_of=current_reference_as_of,
        current_reference_price_date=current_record.price_date,
        current_per=current_per,
        current_per_observation_id=current_per_observation_id,
        percentile_method=PERCENTILE_METHOD_EMPIRICAL_CDF_LE,
        percentile_scale=PERCENTILE_SCALE_PERCENT_0_100,
        current_percentile=current_percentile,
        current_minus_historical_median=current_minus_historical_median,
        context_status=HistoricalContextStatus.PARTIAL,
        attempted_anchor_count=attempted_anchor_count,
        excluded_future_anchor_count=excluded_future_anchor_count,
        unavailable_denominator_count=unavailable_denominator_count,
        corporate_action_excluded_count=corporate_action_excluded_count,
        available_at=available_at,
    )


__all__ = ["build_latest_reported_fy_per_historical_context"]
