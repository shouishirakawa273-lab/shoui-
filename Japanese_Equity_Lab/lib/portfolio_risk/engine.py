"""D0112: exact capital/constraint checks and conditional weighted net returns."""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Context, Decimal, DecimalException, DivisionByZero, InvalidOperation, Overflow, localcontext
from fractions import Fraction

from lib.evaluation.integrity import compute_record_hash, verify_record_integrity
from lib.evidence.thesis_impact import ThesisScenario
from lib.scenario_returns import ReturnComparison

CONTRACT = "D0112_DECIMAL50_HALF_EVEN_E999999_EXACT_LIMITS_V1"
SCENARIOS = (ThesisScenario.BULL, ThesisScenario.BASE, ThesisScenario.BEAR)
UNSUPPORTED = ("THEME", "EVENT", "LIQUIDITY", "CORRELATION", "VAR", "CVAR", "STRESS_CALIBRATION")


@dataclass(frozen=True, kw_only=True)
class PortfolioPolicy:
    policy_id: str
    source_ref: str
    available_at: datetime
    max_company: Decimal
    max_sector: Decimal
    minimum_cash: Decimal


@dataclass(frozen=True, kw_only=True)
class PortfolioPosition:
    position_id: str
    capital_weight: Decimal
    comparison: ReturnComparison
    sector: str
    sector_ref: str
    sector_available_at: datetime


@dataclass(frozen=True, kw_only=True)
class PortfolioRequest:
    request_id: str
    positions: tuple[PortfolioPosition, ...]
    cash_weight: Decimal
    policy: PortfolioPolicy
    currency: str
    decision_cutoff: datetime
    exit_at: datetime
    joint_scenario_ref: str
    joint_scenario_available_at: datetime
    joint_comparison_hashes: tuple[str, ...]
    cash_zero_return_ref: str
    cash_available_at: datetime
    calculated_at: datetime
    synthetic: bool
    record_hash: str


@dataclass(frozen=True, kw_only=True)
class PortfolioScenario:
    scenario: ThesisScenario
    baseline_net_return: Decimal
    replay_net_return: Decimal
    replay_minus_baseline: Decimal


@dataclass(frozen=True, kw_only=True)
class PortfolioResult:
    request: PortfolioRequest
    request_hash: str
    comparison_hashes: tuple[str, ...]
    company_weights: tuple[tuple[str, Decimal], ...]
    sector_weights: tuple[tuple[str, Decimal], ...]
    cash_weight: Decimal
    scenarios: tuple[PortfolioScenario, ...]
    baseline_downside: Decimal
    replay_downside: Decimal
    downside_delta: Decimal
    breaches: tuple[str, ...]
    declared_constraints_pass: bool
    unsupported_checks: tuple[str, ...]
    labels: tuple[str, ...]
    calculation_contract_version: str
    record_hash: str


def _seal(record):
    return replace(record, record_hash=compute_record_hash({f.name: getattr(record, f.name) for f in fields(record)}))


def make_request(
    *,
    request_id: str,
    positions: tuple[PortfolioPosition, ...],
    cash_weight: Decimal,
    policy: PortfolioPolicy,
    currency: str,
    decision_cutoff: datetime,
    exit_at: datetime,
    joint_scenario_ref: str,
    joint_scenario_available_at: datetime,
    joint_comparison_hashes: tuple[str, ...],
    cash_zero_return_ref: str,
    cash_available_at: datetime,
    calculated_at: datetime,
    synthetic: bool,
) -> PortfolioRequest:
    """Canonicalize new request order; never modify an existing input record."""
    if not isinstance(positions, tuple) or any(not isinstance(p, PortfolioPosition) for p in positions):
        raise ValueError("immutable typed positions required")
    for position in positions:
        _text(position.position_id)
    if not isinstance(joint_comparison_hashes, tuple):
        raise ValueError("immutable attestation binding required")
    for record_hash in joint_comparison_hashes:
        _text(record_hash)
    return _seal(
        PortfolioRequest(
            request_id=request_id,
            positions=tuple(sorted(positions, key=lambda p: p.position_id)),
            cash_weight=cash_weight,
            policy=policy,
            currency=currency,
            decision_cutoff=decision_cutoff,
            exit_at=exit_at,
            joint_scenario_ref=joint_scenario_ref,
            joint_scenario_available_at=joint_scenario_available_at,
            joint_comparison_hashes=tuple(sorted(joint_comparison_hashes)),
            cash_zero_return_ref=cash_zero_return_ref,
            cash_available_at=cash_available_at,
            calculated_at=calculated_at,
            synthetic=synthetic,
            record_hash="",
        )
    )


def _text(value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("nonempty metadata required")


def _time(value: datetime) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("aware timestamp required")


def _number(value: object) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError("finite Decimal required")


def _validate(request: PortfolioRequest) -> None:
    if (
        not isinstance(request, PortfolioRequest)
        or not isinstance(request.policy, PortfolioPolicy)
        or not isinstance(request.positions, tuple)
        or any(not isinstance(p, PortfolioPosition) or not isinstance(p.comparison, ReturnComparison) for p in request.positions)
        or not isinstance(request.joint_comparison_hashes, tuple)
    ):
        raise ValueError("immutable typed request required")
    for position in request.positions:
        _text(position.position_id)
    for record_hash in request.joint_comparison_hashes:
        _text(record_hash)
    if not verify_record_integrity(request):
        raise ValueError("request integrity failure")
    policy = request.policy
    for value in (
        request.request_id,
        request.currency,
        request.joint_scenario_ref,
        request.cash_zero_return_ref,
        policy.policy_id,
        policy.source_ref,
    ):
        _text(value)
    for stamp in (
        request.decision_cutoff,
        request.exit_at,
        request.calculated_at,
        request.joint_scenario_available_at,
        request.cash_available_at,
        policy.available_at,
    ):
        _time(stamp)
    if not request.decision_cutoff < request.exit_at or request.calculated_at < request.decision_cutoff:
        raise ValueError("invalid common time ordering")
    if max(request.joint_scenario_available_at, request.cash_available_at, policy.available_at) > request.decision_cutoff:
        raise ValueError("future attestation, cash assumption or policy")
    if type(request.synthetic) is not bool:
        raise ValueError("explicit mode required")
    for amount in (request.cash_weight, policy.max_company, policy.max_sector, policy.minimum_cash):
        _number(amount)
        if not 0 <= amount <= 1:
            raise ValueError("fraction outside zero-one range")
    if (
        not isinstance(request.positions, tuple)
        or tuple(sorted(request.positions, key=lambda p: p.position_id)) != request.positions
        or len({p.position_id for p in request.positions}) != len(request.positions)
    ):
        raise ValueError("unique canonical immutable positions required")
    expected_hashes = tuple(sorted(p.comparison.record_hash for p in request.positions))
    if request.joint_comparison_hashes != expected_hashes:
        raise ValueError("joint scenario attestation binding mismatch")
    total = Fraction(request.cash_weight)
    company_sectors: dict[str, str] = {}
    for position in request.positions:
        _text(position.position_id)
        _text(position.sector)
        _text(position.sector_ref)
        if position.sector.strip().upper() in ("UNKNOWN", "UNCLASSIFIED"):
            raise ValueError("unknown sector")
        _time(position.sector_available_at)
        if position.sector_available_at > request.decision_cutoff:
            raise ValueError("future sector evidence")
        _number(position.capital_weight)
        if position.capital_weight <= 0:
            raise ValueError("positive capital weight required")
        total += Fraction(position.capital_weight)
        comparison = position.comparison
        if not verify_record_integrity(comparison) or comparison.terms_hash != compute_record_hash({"terms": comparison.terms}):
            raise ValueError("comparison integrity failure")
        terms = comparison.terms
        entity = terms.price.entity_id
        _text(entity)
        _time(comparison.calculated_at)
        _time(terms.decision_cutoff)
        _time(terms.exit_mapping.exit_at)
        if (
            terms.price.currency != request.currency
            or terms.cash.currency != request.currency
            or terms.decision_cutoff != request.decision_cutoff
            or terms.exit_mapping.exit_at != request.exit_at
            or not request.decision_cutoff <= comparison.calculated_at <= request.calculated_at
        ):
            raise ValueError("constituent common terms mismatch")
        if type(terms.synthetic) is not bool or (not request.synthetic and (terms.synthetic or "SYNTHETIC" in comparison.labels)):
            raise ValueError("synthetic constituent in real mode")
        if entity in company_sectors and company_sectors[entity] != position.sector:
            raise ValueError("inconsistent sector for same company")
        company_sectors[entity] = position.sector
        if (
            not isinstance(comparison.scenarios, tuple)
            or len(comparison.scenarios) != 3
            or {s.scenario for s in comparison.scenarios} != set(SCENARIOS)
            or any(not isinstance(s.scenario, ThesisScenario) for s in comparison.scenarios)
        ):
            raise ValueError("three unique typed constituent scenarios required")
        for scenario in comparison.scenarios:
            for metrics in (scenario.baseline, scenario.replay, scenario.replay_minus_baseline):
                for number in (metrics.valuation_gap, metrics.gross_return, metrics.net_before_tax_return):
                    _number(number)
        for number in (comparison.baseline_downside, comparison.replay_downside, comparison.downside_delta):
            _number(number)
    if total != 1:
        raise ValueError("capital weights must sum exactly to one")


def evaluate_portfolio_risk(request: PortfolioRequest) -> PortfolioResult:
    """Consume existing return arithmetic; enforce only the declared three constraints."""
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
    try:
        with localcontext(context):
            _validate(request)
            company: dict[str, Fraction] = {}
            sector: dict[str, Fraction] = {}
            for position in request.positions:
                entity = position.comparison.terms.price.entity_id
                company[entity] = company.get(entity, Fraction(0)) + Fraction(position.capital_weight)
                sector[position.sector] = sector.get(position.sector, Fraction(0)) + Fraction(position.capital_weight)
            breaches = tuple(
                [f"COMPANY:{key}" for key in sorted(company) if company[key] > Fraction(request.policy.max_company)]
                + [f"SECTOR:{key}" for key in sorted(sector) if sector[key] > Fraction(request.policy.max_sector)]
                + (["CASH_MINIMUM"] if Fraction(request.cash_weight) < Fraction(request.policy.minimum_cash) else [])
            )
            scenarios = []
            for scenario in SCENARIOS:
                baseline = Decimal(0)
                replay = Decimal(0)
                for position in request.positions:
                    values = next(s for s in position.comparison.scenarios if s.scenario is scenario)
                    baseline += position.capital_weight * values.baseline.net_before_tax_return
                    replay += position.capital_weight * values.replay.net_before_tax_return
                scenarios.append(
                    PortfolioScenario(
                        scenario=scenario,
                        baseline_net_return=baseline,
                        replay_net_return=replay,
                        replay_minus_baseline=replay - baseline,
                    )
                )
            ld = max(Decimal(0), -scenarios[2].baseline_net_return)
            rd = max(Decimal(0), -scenarios[2].replay_net_return)

            def decimal(value: Fraction) -> Decimal:
                return Decimal(value.numerator) / Decimal(value.denominator)

            result = PortfolioResult(
                request=request,
                request_hash=request.record_hash,
                comparison_hashes=request.joint_comparison_hashes,
                company_weights=tuple((key, decimal(company[key])) for key in sorted(company)),
                sector_weights=tuple((key, decimal(sector[key])) for key in sorted(sector)),
                cash_weight=request.cash_weight,
                scenarios=tuple(scenarios),
                baseline_downside=ld,
                replay_downside=rd,
                downside_delta=rd - ld,
                breaches=breaches,
                declared_constraints_pass=not breaches,
                unsupported_checks=UNSUPPORTED,
                labels=(
                    "CALLER_ATTESTED_JOINT_SCENARIOS",
                    "CONDITIONAL_ONLY",
                    "PRE_TAX",
                    "NON_ANNUALIZED",
                    "NO_PROBABILITY_WEIGHTING",
                    "NOT_PORTFOLIO_OPTIMIZATION",
                    "SOURCE_ARITHMETIC_NOT_REVALIDATED",
                    "CAPITAL_WEIGHTS_INCLUDE_ENTRY_COSTS",
                    "CASH_ZERO_RETURN_ASSUMPTION",
                    "SYNTHETIC" if request.synthetic else "NOT_EMPIRICALLY_VALIDATED",
                ),
                calculation_contract_version=CONTRACT,
                record_hash="",
            )
            return _seal(result)
    except DecimalException as error:
        raise ValueError("portfolio decimal arithmetic outside supported context") from error
