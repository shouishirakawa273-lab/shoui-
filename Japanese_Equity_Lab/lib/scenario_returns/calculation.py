"""D0111 v1: conditional, pre-tax, non-annualized decimal ratios.

Source hashes certify internal integrity, not economic truth or source arithmetic.
Frozen valuation arithmetic is consumed as supplied, never recomputed here.
Share basis and exit mapping are caller attestations, not independent certification.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Context, Decimal, DecimalException, DivisionByZero, InvalidOperation, Overflow, localcontext

from lib.evaluation.integrity import compute_record_hash, verify_record_integrity
from lib.evidence.thesis_impact import ThesisScenario
from lib.valuation.forward_reverse_model import ValuationResult, ValuationStatus

CONTRACT = "D0111_DECIMAL_50_HALF_EVEN_E999999_V1"
SCENARIOS = (ThesisScenario.BULL, ThesisScenario.BASE, ThesisScenario.BEAR)


@dataclass(frozen=True, kw_only=True)
class PriceReference:
    price_id: str
    entity_id: str
    currency: str
    value: Decimal
    observed_at: datetime
    available_at: datetime
    source_ref: str


@dataclass(frozen=True, kw_only=True)
class CashTerms:
    dividend: Decimal
    entry_cost: Decimal
    exit_cost: Decimal
    currency: str
    source_ref: str
    available_at: datetime
    coverage_start: datetime
    coverage_end: datetime


@dataclass(frozen=True, kw_only=True)
class ExitMapping:
    target_period: str
    exit_at: datetime
    evidence_ref: str
    available_at: datetime


@dataclass(frozen=True, kw_only=True)
class ShareBasisAttestation:
    baseline_hash: str
    replay_hash: str
    price_id: str
    share_count: Decimal
    price_basis_ref: str
    baseline_basis_ref: str
    replay_basis_ref: str
    confirmed: bool
    available_at: datetime


@dataclass(frozen=True, kw_only=True)
class SharedTerms:
    price: PriceReference
    cash: CashTerms
    exit_mapping: ExitMapping
    basis: ShareBasisAttestation
    decision_cutoff: datetime
    macro_scenarios: tuple[ThesisScenario, ...]
    macro_reference: str
    synthetic: bool


@dataclass(frozen=True, kw_only=True)
class ReturnMetrics:
    valuation_gap: Decimal
    gross_return: Decimal
    net_before_tax_return: Decimal


@dataclass(frozen=True, kw_only=True)
class ScenarioPair:
    scenario: ThesisScenario
    baseline: ReturnMetrics
    replay: ReturnMetrics
    replay_minus_baseline: ReturnMetrics


@dataclass(frozen=True, kw_only=True)
class ReturnComparison:
    baseline_hash: str
    replay_hash: str
    baseline_reference: str
    replay_reference: str
    terms: SharedTerms
    terms_hash: str
    calculated_at: datetime
    scenarios: tuple[ScenarioPair, ...]
    baseline_downside: Decimal
    replay_downside: Decimal
    downside_delta: Decimal
    labels: tuple[str, ...]
    calculation_contract_version: str
    record_hash: str


def _text(value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("nonempty reference required")


def _aware(value: datetime) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("aware timestamp required")


def _decimal(value: object, *, minimum: Decimal | None = None) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError("finite Decimal required")
    if minimum is not None and value < minimum:
        raise ValueError("value below allowed minimum")


def _validate(baseline: ValuationResult, replay: ValuationResult, terms: SharedTerms, at: datetime) -> None:
    p, c, m, b = terms.price, terms.cash, terms.exit_mapping, terms.basis
    cutoff = terms.decision_cutoff
    for stamp in (
        at,
        cutoff,
        p.observed_at,
        p.available_at,
        c.available_at,
        c.coverage_start,
        c.coverage_end,
        m.exit_at,
        m.available_at,
        b.available_at,
    ):
        _aware(stamp)
    for value in (
        p.price_id,
        p.entity_id,
        p.currency,
        p.source_ref,
        c.currency,
        c.source_ref,
        m.target_period,
        m.evidence_ref,
        b.baseline_hash,
        b.replay_hash,
        b.price_id,
        b.price_basis_ref,
        b.baseline_basis_ref,
        b.replay_basis_ref,
        terms.macro_reference,
    ):
        _text(value)
    if type(terms.synthetic) is not bool or type(b.confirmed) is not bool or not b.confirmed:
        raise ValueError("explicit data mode and confirmed caller basis required")
    if not isinstance(terms.macro_scenarios, tuple) or not terms.macro_scenarios:
        raise ValueError("explicit macro scenario roster required")
    if any(not isinstance(s, ThesisScenario) or s not in SCENARIOS for s in terms.macro_scenarios) or len(
        set(terms.macro_scenarios)
    ) != len(terms.macro_scenarios):
        raise ValueError("invalid macro scenario roster")
    _decimal(p.value, minimum=Decimal(0))
    _decimal(b.share_count, minimum=Decimal(0))
    if p.value == 0 or b.share_count == 0:
        raise ValueError("positive price and shares required")
    for cash_value in (c.dividend, c.entry_cost, c.exit_cost):
        _decimal(cash_value, minimum=Decimal(0))
    if not (p.observed_at <= p.available_at <= cutoff < m.exit_at and cutoff <= at):
        raise ValueError("price/cutoff/exit ordering invalid")
    if max(c.available_at, m.available_at, b.available_at) > cutoff or c.coverage_start != cutoff or c.coverage_end != m.exit_at:
        raise ValueError("cash, mapping or basis PIT/coverage invalid")
    if b.baseline_hash != baseline.record_hash or b.replay_hash != replay.record_hash or b.price_id != p.price_id:
        raise ValueError("basis binding mismatch")
    for result in (baseline, replay):
        if not verify_record_integrity(result):
            raise ValueError("valuation integrity failure")
        if result.status is not ValuationStatus.SUCCESS:
            raise ValueError("successful valuation required")
        _aware(result.evidence_cutoff)
        _aware(result.calculated_at)
        if not (result.evidence_cutoff == cutoff <= result.calculated_at <= at):
            raise ValueError("valuation timestamp mismatch")
        for value in (
            result.result_id,
            result.entity_id,
            result.valuation_model_id,
            result.valuation_model_version,
            result.target_period,
            result.input_forecast_reference,
        ):
            _text(value)
        if (
            result.entity_id != p.entity_id
            or result.currency != p.currency
            or c.currency != p.currency
            or result.target_period != m.target_period
        ):
            raise ValueError("identity/currency/period mismatch")
        multiple, bs = result.multiple_used, result.balance_sheet_used
        if multiple is None or bs is None:
            raise ValueError("multiple and balance sheet required")
        for stamp in (multiple.available_at, bs.net_debt_available_at, bs.share_count_available_at):
            if stamp is None:
                raise ValueError("missing balance sheet availability")
            _aware(stamp)
            if stamp > cutoff:
                raise ValueError("valuation input PIT invalid")
        _decimal(multiple.value, minimum=Decimal(0))
        _decimal(bs.net_debt)
        _decimal(bs.share_count, minimum=Decimal(0))
        if multiple.value == 0 or bs.share_count != b.share_count or bs.net_debt_currency != p.currency:
            raise ValueError("multiple, share basis or balance currency mismatch")
        for value in (multiple.reference_period, multiple.method_version, bs.source_id):
            _text(value)
        if (
            not isinstance(result.scenarios, tuple)
            or len(result.scenarios) != 3
            or {s.scenario for s in result.scenarios} != set(SCENARIOS)
            or any(not isinstance(s.scenario, ThesisScenario) for s in result.scenarios)
        ):
            raise ValueError("three unique scenarios required")
        for s in result.scenarios:
            if s.currency != p.currency:
                raise ValueError("scenario currency mismatch")
            for value in (s.input_operating_income, s.estimated_enterprise_value, s.estimated_equity_value):
                _decimal(value)
            _decimal(s.estimated_value_per_share, minimum=Decimal(0))
    if (
        baseline.valuation_model_id != replay.valuation_model_id
        or baseline.valuation_model_version != replay.valuation_model_version
        or baseline.multiple_used != replay.multiple_used
        or baseline.balance_sheet_used != replay.balance_sheet_used
    ):
        raise ValueError("comparison model/multiple/balance conditions differ")
    left = {s.scenario: s for s in baseline.scenarios}
    right = {s.scenario: s for s in replay.scenarios}
    if any(left[s] != right[s] for s in SCENARIOS if s not in terms.macro_scenarios):
        raise ValueError("non-target scenario changed")


def _compare_scenario_returns(
    *, baseline: ValuationResult, replay: ValuationResult, terms: SharedTerms, calculated_at: datetime
) -> ReturnComparison:
    """Reject invalid inputs with ValueError; never return partial success.

    Existing valuation amounts are not independently recomputed or certified.
    A single shared immutable terms object applies identically to both arms.
    """
    context = Context(
        prec=50,
        rounding=ROUND_HALF_EVEN,
        Emin=-999999,
        Emax=999999,
        capitals=1,
        clamp=0,
        flags=[],
        traps=[InvalidOperation, DivisionByZero, Overflow],
    )
    with localcontext(context):
        _validate(baseline, replay, terms, calculated_at)
        p, c = terms.price.value, terms.cash

        def metrics(value: Decimal) -> ReturnMetrics:
            return ReturnMetrics(
                valuation_gap=(value - p) / p,
                gross_return=(value + c.dividend - p) / p,
                net_before_tax_return=(value + c.dividend - c.exit_cost - p - c.entry_cost) / (p + c.entry_cost),
            )

        pairs = []
        for scenario in SCENARIOS:
            lv = next(s.estimated_value_per_share for s in baseline.scenarios if s.scenario is scenario)
            rv = next(s.estimated_value_per_share for s in replay.scenarios if s.scenario is scenario)
            assert lv is not None and rv is not None
            left_metrics, right_metrics = metrics(lv), metrics(rv)
            delta = ReturnMetrics(
                valuation_gap=right_metrics.valuation_gap - left_metrics.valuation_gap,
                gross_return=right_metrics.gross_return - left_metrics.gross_return,
                net_before_tax_return=right_metrics.net_before_tax_return - left_metrics.net_before_tax_return,
            )
            pairs.append(
                ScenarioPair(scenario=scenario, baseline=left_metrics, replay=right_metrics, replay_minus_baseline=delta)
            )
        bear = pairs[2]
        ld = max(Decimal(0), -bear.baseline.net_before_tax_return)
        rd = max(Decimal(0), -bear.replay.net_before_tax_return)
        payload = dict(
            baseline_hash=baseline.record_hash,
            replay_hash=replay.record_hash,
            baseline_reference=baseline.result_id,
            replay_reference=replay.result_id,
            terms=terms,
            terms_hash=compute_record_hash({"terms": terms}),
            calculated_at=calculated_at,
            scenarios=tuple(pairs),
            baseline_downside=ld,
            replay_downside=rd,
            downside_delta=rd - ld,
            labels=(
                "SCENARIO_IMPLIED",
                "OBSERVATIONAL_ONLY",
                "NO_PROBABILITY_WEIGHTING",
                "CALLER_ATTESTED_BASIS",
                "SOURCE_ARITHMETIC_NOT_REVALIDATED",
                "PRE_TAX",
                "NON_ANNUALIZED",
                "NOT_EXECUTION_REPLAY",
                "SYNTHETIC" if terms.synthetic else "REAL_INPUTS_NOT_EMPIRICALLY_VALIDATED",
            ),
            calculation_contract_version=CONTRACT,
        )
        return ReturnComparison(**payload, record_hash=compute_record_hash(payload))


def compare_scenario_returns(
    *, baseline: ValuationResult, replay: ValuationResult, terms: SharedTerms, calculated_at: datetime
) -> ReturnComparison:
    """Return a complete comparison or ValueError, including decimal range failure."""
    try:
        return _compare_scenario_returns(baseline=baseline, replay=replay, terms=terms, calculated_at=calculated_at)
    except DecimalException as error:
        raise ValueError("D0111 decimal arithmetic outside supported context") from error
