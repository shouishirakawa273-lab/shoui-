"""Exact rational caps and downward grid allocation under explicit caller priority."""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Context, Decimal, DecimalException, DivisionByZero, InvalidOperation, Overflow, localcontext
from fractions import Fraction

from lib.evaluation.integrity import compute_record_hash, verify_record_integrity
from lib.portfolio_risk import PortfolioRequest, PortfolioResult, evaluate_portfolio_risk, make_request

CONTRACT = "D0113_EXACT_CAPS_PRIORITY_GRID_V1"


@dataclass(frozen=True, kw_only=True)
class ConstructionRequest:
    request_id: str
    desired: PortfolioRequest
    priority: tuple[str, ...]
    allocation_quantum: Decimal
    policy_ref: str
    policy_available_at: datetime
    calculated_at: datetime
    record_hash: str


@dataclass(frozen=True, kw_only=True)
class PositionAudit:
    position_id: str
    priority_rank: int
    desired_weight: Decimal
    allocated_weight: Decimal
    reduction: Decimal
    reasons: tuple[str, ...]
    policy_ref: str


@dataclass(frozen=True, kw_only=True)
class ConstructionResult:
    request: ConstructionRequest
    request_hash: str
    audit: tuple[PositionAudit, ...]
    output_request: PortfolioRequest
    output_risk: PortfolioResult
    released_cash: Decimal
    labels: tuple[str, ...]
    unsupported_checks: tuple[str, ...]
    rule_version: str
    record_hash: str


def _seal(record):
    return replace(record, record_hash=compute_record_hash({f.name: getattr(record, f.name) for f in fields(record)}))


def _text(value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("nonempty metadata required")


def _time(value: datetime) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("aware timestamp required")


def _decimal(value: Fraction) -> Decimal:
    """Construct an exact terminating Decimal, without caller-context arithmetic."""
    numerator, denominator = value.numerator, value.denominator
    twos = fives = 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    if denominator != 1:
        raise ValueError("allocation must be terminating decimal")
    scale = max(twos, fives)
    coefficient = abs(numerator) * 2 ** (scale - twos) * 5 ** (scale - fives)
    return Decimal((int(numerator < 0), tuple(int(d) for d in str(coefficient)), -scale))


def make_construction_request(
    *,
    request_id: str,
    desired: PortfolioRequest,
    priority: tuple[str, ...],
    allocation_quantum: Decimal,
    policy_ref: str,
    policy_available_at: datetime,
    calculated_at: datetime,
) -> ConstructionRequest:
    return _seal(
        ConstructionRequest(
            request_id=request_id,
            desired=desired,
            priority=priority,
            allocation_quantum=allocation_quantum,
            policy_ref=policy_ref,
            policy_available_at=policy_available_at,
            calculated_at=calculated_at,
            record_hash="",
        )
    )


def construct_portfolio(request: ConstructionRequest) -> ConstructionResult:
    """Validate all desired inputs before selection, then re-evaluate every output."""
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
            if not isinstance(request, ConstructionRequest) or not isinstance(request.desired, PortfolioRequest):
                raise ValueError("typed immutable request required")
            _text(request.request_id)
            _text(request.policy_ref)
            _time(request.policy_available_at)
            _time(request.calculated_at)
            if not isinstance(request.priority, tuple) or any(not isinstance(p, str) for p in request.priority):
                raise ValueError("immutable explicit priority required")
            quantum = request.allocation_quantum
            if not isinstance(quantum, Decimal) or not quantum.is_finite():
                raise ValueError("finite Decimal quantum required")
            if not verify_record_integrity(request):
                raise ValueError("construction integrity failure")
            desired = request.desired
            # Invalid constituents must never disappear because allocation would be zero.
            evaluate_portfolio_risk(desired)
            if request.calculated_at < desired.calculated_at or request.policy_available_at > desired.decision_cutoff:
                raise ValueError("construction policy/calculation PIT invalid")
            q = Fraction(quantum)
            if q not in tuple(Fraction(1, 10**n) for n in range(13)):
                raise ValueError("quantum must be power of ten from one to 1e-12")
            ids = {p.position_id for p in desired.positions}
            if len(request.priority) != len(ids) or set(request.priority) != ids:
                raise ValueError("priority must contain every desired position exactly once")
            budget = 1 - max(Fraction(desired.cash_weight), Fraction(desired.policy.minimum_cash))
            company: dict[str, Fraction] = {}
            sector: dict[str, Fraction] = {}
            selected = []
            audit = []
            for rank, position_id in enumerate(request.priority, start=1):
                position = next(p for p in desired.positions if p.position_id == position_id)
                entity = position.comparison.terms.price.entity_id
                wanted = Fraction(position.capital_weight)
                company_cap = Fraction(desired.policy.max_company) - company.get(entity, Fraction(0))
                sector_cap = Fraction(desired.policy.max_sector) - sector.get(position.sector, Fraction(0))
                capped = max(Fraction(0), min(wanted, company_cap, sector_cap, budget))
                allocated = (capped // q) * q
                reasons = []
                if allocated < wanted:
                    if company_cap < wanted and company_cap == capped:
                        reasons.append("COMPANY_LIMIT")
                    if sector_cap < wanted and sector_cap == capped:
                        reasons.append("SECTOR_LIMIT")
                    if budget < wanted and budget == capped:
                        reasons.append("CASH_OR_BUDGET_LIMIT")
                    if allocated < capped:
                        reasons.append("GRID_FLOOR")
                if not reasons:
                    reasons.append("UNCHANGED")
                audit.append(
                    PositionAudit(
                        position_id=position_id,
                        priority_rank=rank,
                        desired_weight=position.capital_weight,
                        allocated_weight=_decimal(allocated),
                        reduction=_decimal(wanted - allocated),
                        reasons=tuple(reasons),
                        policy_ref=request.policy_ref,
                    )
                )
                if allocated > 0:
                    selected.append(replace(position, capital_weight=_decimal(allocated)))
                company[entity] = company.get(entity, Fraction(0)) + allocated
                sector[position.sector] = sector.get(position.sector, Fraction(0)) + allocated
                budget -= allocated
            cash = 1 - sum((Fraction(p.capital_weight) for p in selected), Fraction(0))
            output = make_request(
                request_id=f"{request.request_id}:CONSTRUCTED",
                positions=tuple(selected),
                cash_weight=_decimal(cash),
                policy=desired.policy,
                currency=desired.currency,
                decision_cutoff=desired.decision_cutoff,
                exit_at=desired.exit_at,
                joint_scenario_ref=f"DERIVED_SUBSET:{desired.record_hash}:{desired.joint_scenario_ref}",
                joint_scenario_available_at=desired.joint_scenario_available_at,
                joint_comparison_hashes=tuple(sorted(p.comparison.record_hash for p in selected)),
                cash_zero_return_ref=desired.cash_zero_return_ref,
                cash_available_at=desired.cash_available_at,
                calculated_at=request.calculated_at,
                synthetic=desired.synthetic,
            )
            risk = evaluate_portfolio_risk(output)
            if not risk.declared_constraints_pass:
                raise ValueError("constructed declared constraints failed")
            result = ConstructionResult(
                request=request,
                request_hash=request.record_hash,
                audit=tuple(audit),
                output_request=output,
                output_risk=risk,
                released_cash=_decimal(cash - Fraction(desired.cash_weight)),
                labels=(
                    "RULE_BASED_NOT_OPTIMAL",
                    "NO_RECOMMENDATION",
                    "INITIAL_CAPITAL_INCLUDES_ENTRY_COSTS",
                    "NO_REDISTRIBUTION",
                    "CALLER_PRIORITY",
                    "FRACTIONAL_WEIGHTS_NOT_EXECUTABLE_ORDERS",
                    "DERIVED_JOINT_SCENARIO_SUBSET",
                    "SYNTHETIC" if desired.synthetic else "NOT_EMPIRICALLY_VALIDATED",
                ),
                unsupported_checks=risk.unsupported_checks,
                rule_version=CONTRACT,
                record_hash="",
            )
            return _seal(result)
    except DecimalException as error:
        raise ValueError("construction decimal arithmetic outside supported context") from error
