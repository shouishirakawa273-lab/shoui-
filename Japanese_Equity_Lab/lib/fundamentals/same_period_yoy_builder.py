"""SAME_PERIOD_YOY_CHANGE_RATIOの選定・計算(Stage 3.12、D0086)。

Price/Corporate Actionを扱わない純Fundamentals-to-Fundamentals Derived
Factのため、`lib.valuation`のBuilderとは独立させた(Price Selectorも
Corporate Action Guardも不要)。ただしTyped Selector + Defense-in-depth
Builderという2層設計(Selector=Filter/Group/Match、Builder=単一Pairへの
再検証)は`lib.valuation.current_fy_forecast_builder`(D0084)と同じ設計を
踏襲する。

**Quarter-only Derivationは行わない(要件v1-3)**: `2Q - 1Q`のような
Standalone化は一切しない。常に「同一Period Type(1Q/2Q/3Q/FYのいずれか)の
Cumulative値 vs 前年同一Period TypeのCumulative値」を比較する。

**Current Period Selection(要件v1-6)**: 1Q/2Q/3Q/FYのうち、`as_of`時点で
利用可能な最新Disclosure Cadenceを「同一Fiscal Year内でpublished_at最大」
というLogicで選ぶ(D0084のTarget FY Grouping + Max Published Atと同型)。
PeriodType Enumの大小だけでは決めない(Provider Schema上1Q<2Q<3Q<FYという
順序保証は無いため)。

**Prior-Year Selection(要件v1-7)**: Currentと同一Period Typeで、Fiscal
Yearがちょうど1年前のCandidateのみを対象とする。Fiscal Calendarのズレで
Same-Period Comparabilityを安全に証明できない場合は`None`(Coverage Gap、
推測で比較しない)。
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from lib.errors import LookAheadBiasError
from lib.evidence.model import SourceVersion, ValueAvailability
from lib.fundamentals.model import ActualOrForecast, ConsolidationScope, DisclosureEnvelope, FundamentalMetric, PeriodBasis
from lib.fundamentals.same_period_yoy_model import ALLOWED_UNDERLYING_METRIC_TYPES, SamePeriodYoYChangeRecord

_CandidateTriple = tuple[SourceVersion, FundamentalMetric, DisclosureEnvelope]


def _require_date(value: date | None, *, label: str) -> date:
    """Contract Filter通過後は非`None`のはずだが、Type Narrowingのため明示的に
    再検証する(Defense-in-depth、`_single_candidate_contract_ok()`が既に
    Noneを除外済みのCandidateにのみ到達する経路)。"""
    if value is None:
        raise ValueError(f"{label}が不明です(fail closed、Contract Filter後は非Noneのはずです)")
    return value


def _require_datetime(value: datetime | None, *, label: str) -> datetime:
    if value is None:
        raise ValueError(f"{label}が不明です(fail closed、Contract Filter後は非Noneのはずです)")
    return value


def _one_fiscal_year_earlier(d: date) -> date:
    """`d`のちょうど1年前の日付(要件v1-5の「Typed Datesから1年前であることを
    確認する」の実装)。2/29等、暦年上1年前が存在しない日は日本の会計年度
    境界(4/1・3/31等)では実質発生しないが、念のためfail-safeに28日へ丸める
    (推測で日付を作らない——月末±1日を無理に補正しない、単に例外を回避する
    ためだけのfallbackであり、この結果が実際の一致判定で使われるのは
    比較対象自体がその日付を持つ場合のみ)。"""
    try:
        return d.replace(year=d.year - 1)
    except ValueError:
        return d.replace(year=d.year - 1, day=28)


def _single_candidate_contract_ok(
    candidate: _CandidateTriple, *, entity_code: str, as_of: datetime, underlying_metric_type: str
) -> bool:
    version, metric, envelope = candidate
    if metric.metric_type != underlying_metric_type:
        return False
    if metric.actual_or_forecast != ActualOrForecast.ACTUAL:
        return False
    if metric.consolidation_scope != ConsolidationScope.CONSOLIDATED:
        return False
    if metric.period_basis != PeriodBasis.CUMULATIVE:
        return False
    if metric.value_availability != ValueAvailability.PRESENT:
        return False
    if metric.value is None:
        return False
    if version.published_at is None or version.published_at > as_of:
        return False
    if metric.metric_id != version.source_version_id:
        return False
    if metric.envelope_id != envelope.envelope_id:
        return False
    if envelope.internal_code != entity_code:
        return False
    if version.source_record_id != metric.series_id:
        return False
    try:
        if Decimal(version.value) != metric.value:
            return False
    except InvalidOperation:
        return False
    if envelope.current_fiscal_year_start is None or envelope.current_fiscal_year_end is None:
        return False
    if envelope.current_period_start is None or envelope.current_period_end is None:
        return False
    return True


def select_same_period_yoy_candidates(
    candidates: Sequence[_CandidateTriple], *, entity_code: str, as_of: datetime, underlying_metric_type: str
) -> tuple[_CandidateTriple, _CandidateTriple] | None:
    """`candidates`(呼び出し側が対象entityの`underlying_metric_type`について
    1Q/2Q/3Q/FY全Period TypeのSeriesから集めた、raw `(SourceVersion,
    FundamentalMetric, DisclosureEnvelope)`のTuple集合、複数Fiscal Year分)
    から、Current(as_of時点で最新のDisclosure Cadence)とPrior(同一Period
    Typeで1年前のFiscal Year)のPairを選ぶ(要件v1-5〜v1-7)。

    **`selected.values()`から適当に1件取ることは禁止**: Series Keyには
    絶対Fiscal Yearが含まれない(`series_id`は`entity|metric_type|
    CURRENT_FISCAL_YEAR|period_type|scope|accounting_standard`のみ)ため、
    このSelector自身がTyped DatesからFiscal Yearを識別し、Grouping・
    Matchingを行う。

    1. §Contractを満たす候補だけ残す(非適合は静かに除外)。
    2. `(current_fiscal_year_start, current_fiscal_year_end, period_type)`
       ごとにGroup化し、同一Groupに複数Candidateがある場合(訂正等)は
       `published_at`最大のものだけを残す(完全同一Duplicateのみ許容、
       値/`metric_id`が異なるTieはAmbiguityとしてfail closed)。
    3. `current_fiscal_year_start`が最大のGroup群を「Current Fiscal
       Year」とし、その中で`published_at`最大のCandidateをCurrentとする
       (Period Type Enumの大小では決めない)。
    4. CurrentのFiscal Yearからちょうど1年前のGroupを探し、Currentと
       **同一Period Type**のCandidateのみをPriorとして採用する(Cadence
       のFallback/代用はしない)。
    5. Prior Groupが存在しない、または同一Period Typeの候補が無ければ
       `None`(Coverage Gap)。

    候補が1件も残らない場合、またはPriorが見つからない場合は`None`。
    """
    if as_of.tzinfo is None:
        raise ValueError("as_of はtz-awareである必要があります")
    if underlying_metric_type not in ALLOWED_UNDERLYING_METRIC_TYPES:
        raise ValueError(
            f"underlying_metric_type({underlying_metric_type!r})はv1で許可された"
            f"{sorted(ALLOWED_UNDERLYING_METRIC_TYPES)}のいずれかである必要があります"
        )

    contract_ok = [
        c
        for c in candidates
        if _single_candidate_contract_ok(c, entity_code=entity_code, as_of=as_of, underlying_metric_type=underlying_metric_type)
    ]
    if not contract_ok:
        return None

    settled: dict[tuple[date, date, str], _CandidateTriple] = {}
    for c in contract_ok:
        _version, metric, envelope = c
        fy_start = _require_date(envelope.current_fiscal_year_start, label="envelope.current_fiscal_year_start")
        fy_end = _require_date(envelope.current_fiscal_year_end, label="envelope.current_fiscal_year_end")
        key = (fy_start, fy_end, metric.period_type.value)
        existing = settled.get(key)
        if existing is None:
            settled[key] = c
            continue
        new_published_at = _require_datetime(c[0].published_at, label="version.published_at")
        existing_published_at = _require_datetime(existing[0].published_at, label="version.published_at")
        if new_published_at > existing_published_at:
            settled[key] = c
        elif new_published_at == existing_published_at:
            if c[1].metric_id != existing[1].metric_id or c[0].value != existing[0].value:
                raise ValueError(
                    f"entity_code={entity_code}: underlying_metric_type={underlying_metric_type!r}のFiscal Year"
                    f"/Period Type Group({key})で、同一published_atのCandidateが複数存在し値/metric_idが"
                    "一致しないため一意に選定できません(fail closed、推測で選ばない)"
                )
        # 同一published_atかつ完全同一(同一metric_id・同一value)ならDuplicateとして既存のまま維持する。

    if not settled:
        return None

    fy_groups: dict[tuple[date, date], list[_CandidateTriple]] = {}
    for (fy_start, fy_end, _pt), c in settled.items():
        fy_groups.setdefault((fy_start, fy_end), []).append(c)

    current_fy = max(fy_groups.keys(), key=lambda fy: fy[0])
    current_group = fy_groups[current_fy]
    current_candidate = max(current_group, key=lambda c: _require_datetime(c[0].published_at, label="version.published_at"))

    prior_fy = (_one_fiscal_year_earlier(current_fy[0]), _one_fiscal_year_earlier(current_fy[1]))
    prior_group = fy_groups.get(prior_fy)
    if not prior_group:
        return None

    current_period_type = current_candidate[1].period_type.value
    prior_matches = [c for c in prior_group if c[1].period_type.value == current_period_type]
    if not prior_matches:
        return None
    if len(prior_matches) > 1:
        raise ValueError(
            f"entity_code={entity_code}: Prior Fiscal Year Group({prior_fy})に同一Period Type"
            f"({current_period_type})のCandidateが複数存在し、一意に選定できません(fail closed)"
        )
    prior_candidate = prior_matches[0]

    current_envelope = current_candidate[2]
    prior_envelope = prior_candidate[2]
    current_period_start = _require_date(current_envelope.current_period_start, label="current_envelope.current_period_start")
    current_period_end = _require_date(current_envelope.current_period_end, label="current_envelope.current_period_end")
    if _one_fiscal_year_earlier(current_period_start) != prior_envelope.current_period_start:
        return None
    if _one_fiscal_year_earlier(current_period_end) != prior_envelope.current_period_end:
        return None

    return current_candidate, prior_candidate


def build_same_period_yoy_change(
    *,
    entity_code: str,
    as_of: datetime,
    underlying_metric_type: str,
    current_version: SourceVersion,
    current_metric: FundamentalMetric,
    current_envelope: DisclosureEnvelope,
    prior_version: SourceVersion,
    prior_metric: FundamentalMetric,
    prior_envelope: DisclosureEnvelope,
) -> SamePeriodYoYChangeRecord | None:
    """SAME_PERIOD_YOY_CHANGE_RATIOをfail closedで構築する(要件v1-9〜12)。

    **Defense-in-depth**: `select_same_period_yoy_candidates()`を経由しない
    直接呼び出しにも安全なよう、Selectorが内部で適用する全Contract
    (Single Candidate Contract + Pairwise Matching Contract)をこの関数
    自身が再検証する。不一致はいずれも`ValueError`(呼び出し側の入力その
    ものが矛盾している場合)または`LookAheadBiasError`(Future Disclosure
    Leakage)。

    **`None`を返す場合(Contract違反ではなく、値が無いことの明示)**:
    - `prior_metric.value <= 0`(要件v1-10: 通常のPercentage Changeとして
      意味が不安定になるため、Ratio Recordを生成しない。ZeroDivisionError
      任せにしない)。
    """
    if as_of.tzinfo is None:
        raise ValueError("as_of はtz-awareである必要があります")
    if underlying_metric_type not in ALLOWED_UNDERLYING_METRIC_TYPES:
        raise ValueError(
            f"underlying_metric_type({underlying_metric_type!r})はv1で許可された"
            f"{sorted(ALLOWED_UNDERLYING_METRIC_TYPES)}のいずれかである必要があります"
        )

    for label, version, metric, envelope in (
        ("current", current_version, current_metric, current_envelope),
        ("prior", prior_version, prior_metric, prior_envelope),
    ):
        if metric.metric_type != underlying_metric_type:
            raise ValueError(f"{label}_metric.metric_type({metric.metric_type!r})が{underlying_metric_type!r}ではありません")
        if metric.actual_or_forecast != ActualOrForecast.ACTUAL:
            raise ValueError(f"{label}_metric.actual_or_forecast({metric.actual_or_forecast.value!r})がACTUALではありません")
        if metric.consolidation_scope != ConsolidationScope.CONSOLIDATED:
            raise ValueError(
                f"{label}_metric.consolidation_scope({metric.consolidation_scope.value!r})がCONSOLIDATEDではありません"
            )
        if metric.period_basis != PeriodBasis.CUMULATIVE:
            raise ValueError(f"{label}_metric.period_basis({metric.period_basis.value!r})がCUMULATIVEではありません")
        if metric.value is None:
            raise ValueError(f"{label}_metric_id={metric.metric_id}: value_availability=PRESENTのはずですがvalueがNoneです")
        if metric.metric_id != version.source_version_id:
            raise ValueError(
                f"{label}_metric.metric_id({metric.metric_id})が{label}_version.source_version_id"
                f"({version.source_version_id})と一致しません"
            )
        if metric.envelope_id != envelope.envelope_id:
            raise ValueError(
                f"{label}_metric.envelope_id({metric.envelope_id})が{label}_envelope.envelope_id"
                f"({envelope.envelope_id})と一致しません"
            )
        if envelope.internal_code != entity_code:
            raise ValueError(
                f"{label}_envelope.internal_code({envelope.internal_code})がentity_code({entity_code})と一致しません"
            )
        if version.source_record_id != metric.series_id:
            raise ValueError(
                f"{label}_version.source_record_id({version.source_record_id})が{label}_metric.series_id"
                f"({metric.series_id})と一致しません"
            )
        try:
            version_value = Decimal(version.value)
        except InvalidOperation as exc:
            raise ValueError(f"{label}_version.value({version.value!r})をDecimalへParseできません") from exc
        if version_value != metric.value:
            raise ValueError(f"{label}_version.value({version_value})が{label}_metric.value({metric.value})と一致しません")
        if version.published_at is None:
            raise ValueError(
                f"{label}_version.source_version_id={version.source_version_id}: published_atがUNKNOWNのため"
                "SAME_PERIOD_YOY_CHANGE_RATIOを計算できません(fail closed、値を推測しない)"
            )
        if version.published_at > as_of:
            raise LookAheadBiasError(
                f"{label}_version.source_version_id={version.source_version_id}: published_at("
                f"{version.published_at.isoformat()})がas_of({as_of.isoformat()})より後です"
                "(Future Disclosure Leakage防止)"
            )
        if envelope.current_fiscal_year_start is None or envelope.current_fiscal_year_end is None:
            raise ValueError(f"{label}_envelope.envelope_id={envelope.envelope_id}: current_fiscal_year_start/endが不明です")
        if envelope.current_period_start is None or envelope.current_period_end is None:
            raise ValueError(f"{label}_envelope.envelope_id={envelope.envelope_id}: current_period_start/endが不明です")

    if current_metric.period_type != prior_metric.period_type:
        raise ValueError(
            f"current_metric.period_type({current_metric.period_type.value!r})とprior_metric.period_type"
            f"({prior_metric.period_type.value!r})が一致しません(同一Cadence同士のみ比較可能)"
        )
    if current_metric.consolidation_scope != prior_metric.consolidation_scope:
        raise ValueError("current/priorのconsolidation_scopeが一致しません")
    if current_metric.period_basis != prior_metric.period_basis:
        raise ValueError("current/priorのperiod_basisが一致しません")
    if current_metric.accounting_standard != prior_metric.accounting_standard:
        raise ValueError(
            f"current_metric.accounting_standard({current_metric.accounting_standard!r})とprior_metric."
            f"accounting_standard({prior_metric.accounting_standard!r})が一致しません(fail closed、"
            "会計基準変更を跨ぐSame-Period比較は行わない)"
        )

    current_fy_start = _require_date(
        current_envelope.current_fiscal_year_start, label="current_envelope.current_fiscal_year_start"
    )
    current_fy_end = _require_date(current_envelope.current_fiscal_year_end, label="current_envelope.current_fiscal_year_end")
    prior_fy_start = _require_date(prior_envelope.current_fiscal_year_start, label="prior_envelope.current_fiscal_year_start")
    prior_fy_end = _require_date(prior_envelope.current_fiscal_year_end, label="prior_envelope.current_fiscal_year_end")
    current_period_start = _require_date(current_envelope.current_period_start, label="current_envelope.current_period_start")
    current_period_end = _require_date(current_envelope.current_period_end, label="current_envelope.current_period_end")
    prior_period_start = _require_date(prior_envelope.current_period_start, label="prior_envelope.current_period_start")
    prior_period_end = _require_date(prior_envelope.current_period_end, label="prior_envelope.current_period_end")
    current_published_at = _require_datetime(current_version.published_at, label="current_version.published_at")
    prior_published_at = _require_datetime(prior_version.published_at, label="prior_version.published_at")

    if _one_fiscal_year_earlier(current_fy_start) != prior_fy_start:
        raise ValueError(
            "prior_envelope.current_fiscal_year_startがcurrent_envelope.current_fiscal_year_startの1年前ではありません"
            "(fail closed、Fiscal Calendarのズレを推測で比較しない)"
        )
    if _one_fiscal_year_earlier(current_fy_end) != prior_fy_end:
        raise ValueError(
            "prior_envelope.current_fiscal_year_endがcurrent_envelope.current_fiscal_year_endの1年前ではありません"
            "(fail closed、Fiscal Calendarのズレを推測で比較しない)"
        )
    if _one_fiscal_year_earlier(current_period_start) != prior_period_start:
        raise ValueError(
            "prior_envelope.current_period_startがcurrent_envelope.current_period_startの1年前ではありません"
            "(fail closed、Same-Period Comparabilityを推測で証明しない)"
        )
    if _one_fiscal_year_earlier(current_period_end) != prior_period_end:
        raise ValueError(
            "prior_envelope.current_period_endがcurrent_envelope.current_period_endの1年前ではありません"
            "(fail closed、Same-Period Comparabilityを推測で証明しない)"
        )

    if prior_metric.value is None or prior_metric.value <= 0:
        # 要件v1-10: Prior<=0からは通常のPercentage Changeとして意味が安定しない。
        # Fundamental Factとしてzero/negativeがPRESENTであること自体は正しいが、
        # Derived Ratioとしてはfail closed(Recordを生成しない、値を補正しない)。
        return None
    if current_metric.value is None:
        raise ValueError(f"current_metric_id={current_metric.metric_id}: value_availability=PRESENTのはずですがvalueがNoneです")

    current_value = current_metric.value
    prior_value = prior_metric.value
    change_ratio = (current_value / prior_value) - 1

    return SamePeriodYoYChangeRecord(
        entity_code=entity_code,
        underlying_metric_type=underlying_metric_type,
        as_of=as_of,
        current_value=current_value,
        current_period_type=current_metric.period_type.value,
        current_period_start=current_period_start,
        current_period_end=current_period_end,
        current_fiscal_year_start=current_fy_start,
        current_fiscal_year_end=current_fy_end,
        current_published_at=current_published_at,
        current_source_version_id=current_version.source_version_id,
        prior_value=prior_value,
        prior_period_start=prior_period_start,
        prior_period_end=prior_period_end,
        prior_fiscal_year_start=prior_fy_start,
        prior_fiscal_year_end=prior_fy_end,
        prior_published_at=prior_published_at,
        prior_source_version_id=prior_version.source_version_id,
        calculation_expression=(
            f"{underlying_metric_type}({current_period_start.isoformat()}.."
            f"{current_period_end.isoformat()})={current_value} / "
            f"{underlying_metric_type}({prior_period_start.isoformat()}.."
            f"{prior_period_end.isoformat()})={prior_value} - 1"
        ),
        change_ratio=change_ratio,
        accounting_standard=current_metric.accounting_standard,
        consolidation_scope=current_metric.consolidation_scope.value,
        period_basis=current_metric.period_basis.value,
    )


__all__ = ["build_same_period_yoy_change", "select_same_period_yoy_candidates"]
