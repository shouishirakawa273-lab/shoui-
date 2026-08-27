"""CURRENT_FY_COMPANY_FORECAST_PERの選定・計算(Stage 3.10、D0084)。

D0077(`lib.valuation.builder`)の`LATEST_REPORTED_FY_PER`(Actual FY実績
Basis)とは、Denominator選定・Target Semantics・Corporate Action Windowが
いずれも異なる。したがって共通Builderへ早期に統合しない(Option A:
新Record + 新Builder、Codex Audit採用方針)。再利用するのは以下の低レベル
Capabilityのみ:

- `lib.valuation.builder.select_latest_close_bar()`(Price PIT Selector)
- `lib.market_calendar.session_close_at()`
- `lib.valuation.builder.has_share_basis_action_in_window()`(Corporate
  Action Window Predicate、Window境界の意味自体はこのModule側で決める)
- `lib.valuation.builder.positive_eps_or_none()`(Non-Positive EPS Guard、
  D0077/D0084共通)
- Decimal Calculation Helperのパターン、Dual-Parent Provenanceのパターン
  (呼び出し側/Test側で再利用、`lib.valuation.evidence`参照)

**Forecast Horizon != Disclosure Current Period(D0083から継続する核心
制約)**: `forecast_period_start`/`forecast_period_end`は常に開示元の
`current_fiscal_year_start`/`.current_fiscal_year_end`であり、その開示の
`current_period_start`/`.current_period_end`(1Q/2Q/3Q等のCumulative
Period)ではない。`disclosure_period_type`はDisclosure Cadenceを表すのみ。

**Coverage Boundary(v1)**: `CURRENT_FISCAL_YEAR`のCompany Forecast EPS
(`metric_type=eps_current_year_forecast`、`source_field=FEPS`)のみを
対象とする。FY決算直後等でFEPSが空・NxFEPSに新年度予想が存在する期間でも
NxFEPSへFallbackしない(`LATEST_COMPANY_FORECAST_FY_PER`のようなGeneric
Metricは今回作らない、Coverage Gapは正しく`None`のまま)。
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from lib.errors import LookAheadBiasError
from lib.evidence.model import SourceVersion, ValueAvailability
from lib.fundamentals.model import ActualOrForecast, ConsolidationScope, DisclosureEnvelope, FiscalYearTarget, FundamentalMetric
from lib.market_calendar import session_close_at
from lib.schemas.price_data import CorporateAction, RawOHLCVBar
from lib.valuation.builder import has_share_basis_action_in_window, positive_eps_or_none, select_latest_close_bar
from lib.valuation.model import (
    DENOMINATOR_TYPE_CURRENT_FY_COMPANY_FORECAST_EPS_CONSOLIDATED,
    CorporateActionBasisStatus,
    CurrentFyCompanyForecastPerRecord,
)

_REQUIRED_METRIC_TYPE = "eps_current_year_forecast"
_REQUIRED_SOURCE_FIELD = "FEPS"

_CandidateTriple = tuple[SourceVersion, FundamentalMetric, DisclosureEnvelope]


def _candidate_satisfies_contract(
    *, version: SourceVersion, metric: FundamentalMetric, envelope: DisclosureEnvelope, entity_code: str, as_of: datetime
) -> bool:
    """§4のCurrent FY Forecast EPS Candidate Contractを全て満たすか(Selector用、
    非適合Candidateは静かに除外する——単一Candidateへの直接呼び出しはBuilder側の
    Defense-in-depth Validationがfail closedで担当する、二重責務ではない)。"""
    if metric.metric_type != _REQUIRED_METRIC_TYPE:
        return False
    if metric.source_field != _REQUIRED_SOURCE_FIELD:
        return False
    if metric.actual_or_forecast != ActualOrForecast.COMPANY_FORECAST:
        return False
    if metric.fiscal_year_target != FiscalYearTarget.CURRENT_FISCAL_YEAR:
        return False
    if metric.consolidation_scope != ConsolidationScope.CONSOLIDATED:
        return False
    if metric.value_availability != ValueAvailability.PRESENT:
        return False
    if metric.value is None or metric.value <= 0:
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
    if envelope.current_fiscal_year_start > envelope.current_fiscal_year_end:
        return False
    return True


def select_current_fy_company_forecast_eps_candidate(
    candidates: Sequence[_CandidateTriple], *, entity_code: str, as_of: datetime
) -> _CandidateTriple | None:
    """`candidates`(呼び出し側が`fundamentals_as_of(availability_semantics=
    MARKET_PUBLIC_AT)`等で個別Seriesごとに選定済みの`(SourceVersion,
    FundamentalMetric, DisclosureEnvelope)`のTuple集合、通常1Q/2Q/3Q/FY等
    複数Cadence分)から、CURRENT_FY_COMPANY_FORECAST_PERのDenominatorとして
    安全に使える1件を選ぶ(要件v1、§5)。

    **`selected.values()`から適当に1件取ることは禁止**: このSelector自身が
    以下を順に適用する。

    1. §4のCandidate Contractを満たす候補だけ残す(非適合は静かに除外)。
    2. `forecast_period_start <= as_of.date() <= forecast_period_end`を
       満たす候補だけ残す(過去/未来のTarget FYを混同しない)。
    3. `(forecast_period_start, forecast_period_end)`をTarget FY識別子として
       Group化する(series_id文字列のfree-form parseはしない)。
    4. 異なるTargetが複数残る場合は`ValueError`でfail closed(推測で選ばない)。
    5. 単一Target内でpublished_at最大のCandidateを選ぶ。
    6. 同一published_atのCandidateが複数あり、値または`metric_id`が異なる
       場合はambiguityとして`ValueError`でfail closed。完全に同一
       (同一`metric_id`・同一`value`)の場合のみ、どちらを返しても結果が
       変わらないため決定的に1件を返す。

    候補が1件も残らない場合(Coverage Gap)は`None`を返す(FY決算直後で
    NxFEPSしか無い期間等)。
    """
    if as_of.tzinfo is None:
        raise ValueError("as_of はtz-awareである必要があります")

    contract_ok = [
        c
        for c in candidates
        if _candidate_satisfies_contract(version=c[0], metric=c[1], envelope=c[2], entity_code=entity_code, as_of=as_of)
    ]
    windowed = [c for c in contract_ok if c[2].current_fiscal_year_start <= as_of.date() <= c[2].current_fiscal_year_end]  # type: ignore[operator]
    if not windowed:
        return None

    targets = {(c[2].current_fiscal_year_start, c[2].current_fiscal_year_end) for c in windowed}
    if len(targets) > 1:
        raise ValueError(
            f"entity_code={entity_code}: as_of({as_of.isoformat()})時点でCurrent FY Company Forecast EPSの"
            f"Target Fiscal Yearが複数存在し、一意に選定できません(fail closed、推測で選ばない): {sorted(targets)}"
        )

    max_published_at = max(c[0].published_at for c in windowed if c[0].published_at is not None)
    winners = [c for c in windowed if c[0].published_at == max_published_at]
    if len(winners) == 1:
        return winners[0]

    first = winners[0]
    for other in winners[1:]:
        if other[1].metric_id != first[1].metric_id or other[0].value != first[0].value:
            raise ValueError(
                f"entity_code={entity_code}: as_of({as_of.isoformat()})時点でpublished_at="
                f"{max_published_at.isoformat() if max_published_at else 'UNKNOWN'}のCandidateが複数存在し、"
                "値/metric_idが一致しないため一意に選定できません(fail closed、推測で選ばない)"
            )
    return first


def build_current_fy_company_forecast_per(
    *,
    entity_code: str,
    as_of: datetime,
    raw_bars: Sequence[RawOHLCVBar],
    corporate_action_events: Sequence[CorporateAction],
    guidance_version: SourceVersion,
    guidance_metric: FundamentalMetric,
    guidance_envelope: DisclosureEnvelope,
) -> CurrentFyCompanyForecastPerRecord | None:
    """CURRENT_FY_COMPANY_FORECAST_PERをfail closedで構築する(§13)。

    **Defense-in-depth**: `select_current_fy_company_forecast_eps_
    candidate()`を経由せずに直接呼び出された場合にも安全なよう、§4の
    Candidate Contractを全てこの関数自身が再検証する(D0083 Guidance
    Converterを代わりのValidatorとして使わない)。

    **`None`の意味(Silent Excludeではなく、値が無いことの明示)**:
    - as_of時点で選定可能なPrice Barが無い、または`close`が無い。
    - as_ofがForecast Period(`forecast_period_start`..`forecast_period_
      end`)の外(誤用に対するfail closed、通常はSelector側で既に排除済み)。
    - Price DateがForecast Period Startより前(Corporate Action Windowが
      逆転するのを防ぐ)。
    - `eps_value <= 0`(Zero/Negative Company Forecast、§10)。
    - Corporate Action GuardがWindow内でEventを検出した(§9)。

    **例外を送出する場合(入力そのものが契約に反する場合)**: `ValueError`
    (Contract違反全般)または`LookAheadBiasError`(`guidance_version.
    published_at`がas_ofより後、Future Disclosure Leakage)。
    """
    if as_of.tzinfo is None:
        raise ValueError("as_of はtz-awareである必要があります")

    if guidance_metric.metric_type != _REQUIRED_METRIC_TYPE:
        raise ValueError(
            f"guidance_metric.metric_type({guidance_metric.metric_type!r})が{_REQUIRED_METRIC_TYPE!r}ではありません(fail closed)"
        )
    if guidance_metric.source_field != _REQUIRED_SOURCE_FIELD:
        raise ValueError(
            f"guidance_metric.source_field({guidance_metric.source_field!r})が{_REQUIRED_SOURCE_FIELD!r}ではありません"
        )
    if guidance_metric.actual_or_forecast != ActualOrForecast.COMPANY_FORECAST:
        raise ValueError(
            f"guidance_metric.actual_or_forecast({guidance_metric.actual_or_forecast.value!r})が"
            "COMPANY_FORECASTではありません(fail closed、実績値ACTUALを混入させない)"
        )
    if guidance_metric.fiscal_year_target != FiscalYearTarget.CURRENT_FISCAL_YEAR:
        raise ValueError(
            f"guidance_metric.fiscal_year_target({guidance_metric.fiscal_year_target.value!r})が"
            "CURRENT_FISCAL_YEARではありません(fail closed、v1はNext-Year Forecast未対応)"
        )
    if guidance_metric.consolidation_scope != ConsolidationScope.CONSOLIDATED:
        raise ValueError(
            f"guidance_metric.consolidation_scope({guidance_metric.consolidation_scope.value!r})が"
            "CONSOLIDATEDではありません(fail closed)"
        )
    if guidance_metric.value is None:
        raise ValueError(f"metric_id={guidance_metric.metric_id}: value_availability=PRESENTのはずですがvalueがNoneです")
    if guidance_metric.metric_id != guidance_version.source_version_id:
        raise ValueError(
            f"guidance_metric.metric_id({guidance_metric.metric_id})がguidance_version.source_version_id"
            f"({guidance_version.source_version_id})と一致しません"
        )
    if guidance_metric.envelope_id != guidance_envelope.envelope_id:
        raise ValueError(
            f"guidance_metric.envelope_id({guidance_metric.envelope_id})がguidance_envelope.envelope_id"
            f"({guidance_envelope.envelope_id})と一致しません"
        )
    if guidance_envelope.internal_code != entity_code:
        raise ValueError(
            f"guidance_envelope.internal_code({guidance_envelope.internal_code})がentity_code({entity_code})と一致しません"
        )
    if guidance_version.source_record_id != guidance_metric.series_id:
        raise ValueError(
            f"guidance_version.source_record_id({guidance_version.source_record_id})が"
            f"guidance_metric.series_id({guidance_metric.series_id})と一致しません"
        )
    try:
        version_value = Decimal(guidance_version.value)
    except InvalidOperation as exc:
        raise ValueError(f"guidance_version.value({guidance_version.value!r})をDecimalへParseできません") from exc
    if version_value != guidance_metric.value:
        raise ValueError(f"guidance_version.value({version_value})がguidance_metric.value({guidance_metric.value})と一致しません")
    if guidance_version.published_at is None:
        raise ValueError(
            f"source_version_id={guidance_version.source_version_id}: published_at(market_public_at)が"
            "UNKNOWNのためCURRENT_FY_COMPANY_FORECAST_PERを計算できません(fail closed、値を推測しない)"
        )
    if guidance_version.published_at > as_of:
        raise LookAheadBiasError(
            f"source_version_id={guidance_version.source_version_id}: published_at("
            f"{guidance_version.published_at.isoformat()})がas_of({as_of.isoformat()})より後です"
            "(Future Disclosure Leakage防止)"
        )
    if guidance_envelope.current_fiscal_year_start is None or guidance_envelope.current_fiscal_year_end is None:
        raise ValueError(
            f"envelope_id={guidance_envelope.envelope_id}: current_fiscal_year_start/endが不明のため"
            "Forecast Period/Corporate Action Guardを実行できません"
        )
    forecast_period_start: date = guidance_envelope.current_fiscal_year_start
    forecast_period_end: date = guidance_envelope.current_fiscal_year_end
    if forecast_period_start > forecast_period_end:
        raise ValueError(
            f"forecast_period_start({forecast_period_start.isoformat()})がforecast_period_end"
            f"({forecast_period_end.isoformat()})より後です"
        )

    # Forecast Horizon Validate(§13の責務、通常はSelector側で既に排除済みの
    # 誤用ケースに備えたDefense-in-depth、fail closed=None)。
    if not (forecast_period_start <= as_of.date() <= forecast_period_end):
        return None

    price_bar = select_latest_close_bar(raw_bars, as_of=as_of)
    if price_bar is None:
        return None
    if price_bar.code != entity_code:
        raise ValueError(f"raw_barsのCode({price_bar.code})がentity_code({entity_code})と一致しません")
    if price_bar.close is None:
        return None
    price_date = price_bar.session_date
    if price_date < forecast_period_start:
        # Price DateがForecast Period Startより前(Corporate Action Windowの
        # 逆転を防ぐ、通常はas_of>=published_atのGuardで排除されるはずだが、
        # 直接呼び出し等の誤用に備えfail closedにする)。
        return None

    if has_share_basis_action_in_window(corporate_action_events, window_start=forecast_period_start, window_end=price_date):
        return None

    eps_value = positive_eps_or_none(guidance_metric.value)
    if eps_value is None:
        # Zero/Negative Company Forecast EPS(§10): FundamentalとしてPRESENTで
        # あること自体は正しいが、Valuation DenominatorとしてはNOT APPLICABLE。
        return None

    price_value = Decimal(str(price_bar.close))
    multiple = price_value / eps_value

    return CurrentFyCompanyForecastPerRecord(
        entity_code=entity_code,
        as_of=as_of,
        price_date=price_date,
        price_value=price_value,
        price_available_at=session_close_at(price_date),
        denominator_type=DENOMINATOR_TYPE_CURRENT_FY_COMPANY_FORECAST_EPS_CONSOLIDATED,
        eps_value=eps_value,
        forecast_period_start=forecast_period_start,
        forecast_period_end=forecast_period_end,
        guidance_published_at=guidance_version.published_at,
        source_version_id=guidance_version.source_version_id,
        source_field=guidance_metric.source_field,
        fiscal_year_target=guidance_metric.fiscal_year_target.value,
        disclosure_period_type=guidance_metric.period_type.value,
        consolidation_scope=guidance_metric.consolidation_scope.value,
        accounting_standard=guidance_metric.accounting_standard,
        calculation_expression=(
            f"price_close({price_date.isoformat()})={price_value} / "
            f"current_fy_company_forecast_eps_consolidated("
            f"{forecast_period_start.isoformat()}..{forecast_period_end.isoformat()})={eps_value}"
        ),
        multiple=multiple,
        corporate_action_basis_status=CorporateActionBasisStatus.CONFIRMED_NO_ACTION,
    )


__all__ = ["build_current_fy_company_forecast_per", "select_current_fy_company_forecast_eps_candidate"]
