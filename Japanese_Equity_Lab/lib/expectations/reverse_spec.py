"""Reverse Valuation Specification + Market-Implied Result Contract(D0108)。

**本Moduleは実際のReverse Valuation Solverを構築しない**(D0108 §7/§20、
Production DCF Engineは将来のD0110の責務)。ここで定義するのは:

1. `ReverseValuationSpec`: 「どの変数を、どの固定Assumption下で解くか」
   を明示するImmutable Specification。
2. `MarketImpliedAssumptionResult`: 将来のD0110 Solverが返すべき
   Typed Outcome Contract。
3. `AssumptionSurface`: 複数未知変数を単一の偽の一意解として扱わない
   ための、明示的なSolution Surface表現。
4. `solve_toy_linear_reverse_valuation()`: Interface自体を検証するためだ
   けの、意図的に単純化したToy Linear Adapter(本番Valuation Formulaでは
   ない、D0108 §20)。

## No False Uniqueness(最重要、D0108 §8)

市場価格は単独では複数の未知Economic Assumptionを一意に決定できない。
`ReverseValuationSpec`は`solve_for_variables`の個数から`solver_mode`を
**呼び出し側の指定ではなく構造的に導出**する(嘘をつけない設計)——
1変数のみ`SINGLE_VARIABLE`、2変数以上は常に`SOLUTION_SURFACE`に固定
される。`SOLUTION_SURFACE`のSpecから単一のScalar解(`MarketImpliedAssu
mptionResult`)を生成することは許可しない——`AssumptionSurface`
(Grid/Feasible Set)としてのみ表現できる(`build_assumption_surface()`
が`solver_mode != SOLUTION_SURFACE`のSpecを拒否し、`solve_toy_linear_
reverse_valuation()`が`solver_mode == SOLUTION_SURFACE`のSpecに対して
常に`UNDERDETERMINED`を返すことで、両方向から矛盾を構造的に防ぐ)。

## Conditional Language Contract(D0108 §9)

「市場はX%の成長を期待している」ではなく「WACC=8%・Margin=10%・
Terminal Growth=1%という固定Assumptionの下で、現在価格はX%の成長率と
整合する」という条件付き主張のみを構築する。`fixed_assumptions`は
Prose注記ではなく`FixedAssumption`のStructured Tupleとして
First-classに保持する(`record_hash`計算対象にも含まれる)。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from lib.errors import LookAheadBiasError
from lib.evaluation.integrity import compute_record_hash
from lib.expectations.model import MarketExpectationsSchemaError, require_nonempty_str, require_tz_aware

TOY_LINEAR_V1 = "TOY_LINEAR_V1"
"""意図的に単純化したToy Valuation Model ID(D0108 §20)。`observed_
market_price = base_price + sensitivity * solve_for_value`という線形
関係のみを仮定する——実際のDCF/Multiple Valuationのいずれでもなく、
Interface自体の検証のみを目的とする(本番Valuation Engineとして
将来提示してはならない、D0108 §20「Do NOT create a simplistic valuation
formula and later present it as a real valuation engine」)。"""


class SolverMode(StrEnum):
    """`ReverseValuationSpec.solve_for_variables`の個数から構造的に
    導出するSolve方式(D0108 §8)。呼び出し側は直接指定できない
    (`build_reverse_valuation_spec()`が`len(solve_for_variables)`から
    自動的に決定する)。"""

    SINGLE_VARIABLE = "SINGLE_VARIABLE"
    SOLUTION_SURFACE = "SOLUTION_SURFACE"


class MarketImpliedResultStatus(StrEnum):
    """`MarketImpliedAssumptionResult.status`(D0108 §10)。"""

    SUCCESS = "SUCCESS"
    UNDERDETERMINED = "UNDERDETERMINED"
    NO_SOLUTION = "NO_SOLUTION"
    MULTIPLE_SOLUTIONS = "MULTIPLE_SOLUTIONS"
    OUT_OF_BOUNDS = "OUT_OF_BOUNDS"
    PIT_INVALID = "PIT_INVALID"
    INVALID_SPEC = "INVALID_SPEC"
    UNSUPPORTED_MODEL = "UNSUPPORTED_MODEL"


@dataclass(kw_only=True, frozen=True)
class FixedAssumption:
    """Reverse Valuationの前提として固定するAssumption(D0108 §7/§9)。
    First-class Structured Fieldとして保持し、Prose注記に留めない。"""

    name: str
    value: Decimal
    unit: str

    def __post_init__(self) -> None:
        require_nonempty_str(self.name, label="FixedAssumption.name")
        require_nonempty_str(self.unit, label="FixedAssumption.unit")


@dataclass(kw_only=True, frozen=True)
class BoundedAssumption:
    """探索範囲/Solver制約として境界を持つAssumption(D0108 §7、
    `solve_for_variables`自身の探索Rangeとしても、補助的なSemi-known
    Inputの許容Rangeとしても使える)。"""

    name: str
    lower_bound: Decimal
    upper_bound: Decimal
    unit: str

    def __post_init__(self) -> None:
        require_nonempty_str(self.name, label="BoundedAssumption.name")
        require_nonempty_str(self.unit, label="BoundedAssumption.unit")
        if self.lower_bound > self.upper_bound:
            raise MarketExpectationsSchemaError(
                f"BoundedAssumption({self.name!r}) の lower_bound({self.lower_bound})が"
                f"upper_bound({self.upper_bound})より大きいです"
            )


@dataclass(kw_only=True, frozen=True)
class SolveForVariable:
    """解くべき対象変数1件(D0108 §7)。"""

    name: str
    unit: str

    def __post_init__(self) -> None:
        require_nonempty_str(self.name, label="SolveForVariable.name")
        require_nonempty_str(self.unit, label="SolveForVariable.unit")


@dataclass(kw_only=True, frozen=True)
class ReverseValuationSpec:
    """Reverse Valuationの入力Specification(D0108 §7)。本Record自身は
    何も解かない——「何を・何の下で解くか」の宣言のみを保持する。
    """

    spec_id: str
    valuation_model_id: str
    valuation_model_version: str
    entity_id: str
    observed_market_price: Decimal
    price_currency: str
    price_observed_at: datetime
    price_available_at: datetime
    price_source_id: str
    solve_for_variables: tuple[SolveForVariable, ...]
    fixed_assumptions: tuple[FixedAssumption, ...]
    bounded_assumptions: tuple[BoundedAssumption, ...]
    solver_mode: SolverMode
    valuation_horizon: str
    created_at: datetime
    record_hash: str

    def __post_init__(self) -> None:
        for name, value in (
            ("spec_id", self.spec_id),
            ("valuation_model_id", self.valuation_model_id),
            ("valuation_model_version", self.valuation_model_version),
            ("entity_id", self.entity_id),
            ("price_currency", self.price_currency),
            ("price_source_id", self.price_source_id),
            ("valuation_horizon", self.valuation_horizon),
        ):
            require_nonempty_str(value, label=name)
        require_tz_aware(self.price_observed_at, label="price_observed_at")
        require_tz_aware(self.price_available_at, label="price_available_at")
        require_tz_aware(self.created_at, label="created_at")
        if len(self.solve_for_variables) == 0:
            raise MarketExpectationsSchemaError("solve_for_variables は最低1件必要です")
        expected_mode = SolverMode.SINGLE_VARIABLE if len(self.solve_for_variables) == 1 else SolverMode.SOLUTION_SURFACE
        if self.solver_mode != expected_mode:
            raise MarketExpectationsSchemaError(
                f"solve_for_variables が{len(self.solve_for_variables)}件のため solver_mode は"
                f"{expected_mode!r} である必要があります(実際: {self.solver_mode!r})——"
                "複数未知変数を単一解として装うことはできません(D0108 §8)"
            )
        solve_for_names = {v.name for v in self.solve_for_variables}
        fixed_names = {a.name for a in self.fixed_assumptions}
        overlap_fixed = solve_for_names & fixed_names
        if overlap_fixed:
            raise MarketExpectationsSchemaError(
                f"solve_for_variables と fixed_assumptions で変数名が重複しています: {sorted(overlap_fixed)}"
                "(同じ変数を固定しつつ解くことはできません)"
            )
        if len(solve_for_names) != len(self.solve_for_variables):
            raise MarketExpectationsSchemaError("solve_for_variables 内に重複した変数名があります")
        if len(fixed_names) != len(self.fixed_assumptions):
            raise MarketExpectationsSchemaError("fixed_assumptions 内に重複した変数名があります")
        bounded_names = {b.name for b in self.bounded_assumptions}
        if len(bounded_names) != len(self.bounded_assumptions):
            raise MarketExpectationsSchemaError(
                "bounded_assumptions 内に重複した変数名があります"
                "(同じ変数名に矛盾する範囲が指定された場合、後勝ちで黙って片方を無視することを防ぐ)"
            )


def build_reverse_valuation_spec(
    *,
    spec_id: str,
    valuation_model_id: str,
    valuation_model_version: str,
    entity_id: str,
    observed_market_price: Decimal,
    price_currency: str,
    price_observed_at: datetime,
    price_available_at: datetime,
    price_source_id: str,
    solve_for_variables: Sequence[SolveForVariable],
    valuation_horizon: str,
    created_at: datetime,
    fixed_assumptions: Sequence[FixedAssumption] = (),
    bounded_assumptions: Sequence[BoundedAssumption] = (),
) -> ReverseValuationSpec:
    """`ReverseValuationSpec`を構築する唯一のEntrypoint(D0108 §7)。

    `solver_mode`はCallerが指定できない——`len(solve_for_variables)`
    から自動導出する(D0108 §8、False Uniquenessを構造的に防ぐ)。
    Tuple Fieldは`name`でCanonical Order(`sorted()`)へ正規化し、入力
    順序に依存しないRecord Identity/Hashを保証する(D0108 §22F)。
    """
    solver_mode = SolverMode.SINGLE_VARIABLE if len(solve_for_variables) == 1 else SolverMode.SOLUTION_SURFACE
    canonical_solve_for = tuple(sorted(solve_for_variables, key=lambda v: v.name))
    canonical_fixed = tuple(sorted(fixed_assumptions, key=lambda a: a.name))
    canonical_bounded = tuple(sorted(bounded_assumptions, key=lambda a: a.name))
    payload = {
        "spec_id": spec_id,
        "valuation_model_id": valuation_model_id,
        "valuation_model_version": valuation_model_version,
        "entity_id": entity_id,
        "observed_market_price": observed_market_price,
        "price_currency": price_currency,
        "price_observed_at": price_observed_at,
        "price_available_at": price_available_at,
        "price_source_id": price_source_id,
        "solve_for_variables": canonical_solve_for,
        "fixed_assumptions": canonical_fixed,
        "bounded_assumptions": canonical_bounded,
        "solver_mode": solver_mode,
        "valuation_horizon": valuation_horizon,
        "created_at": created_at,
    }
    return ReverseValuationSpec(
        spec_id=spec_id,
        valuation_model_id=valuation_model_id,
        valuation_model_version=valuation_model_version,
        entity_id=entity_id,
        observed_market_price=observed_market_price,
        price_currency=price_currency,
        price_observed_at=price_observed_at,
        price_available_at=price_available_at,
        price_source_id=price_source_id,
        solve_for_variables=canonical_solve_for,
        fixed_assumptions=canonical_fixed,
        bounded_assumptions=canonical_bounded,
        solver_mode=solver_mode,
        valuation_horizon=valuation_horizon,
        created_at=created_at,
        record_hash=compute_record_hash(payload),
    )


@dataclass(kw_only=True, frozen=True)
class SolvedVariable:
    """解けた変数1件の値(D0108 §10)。"""

    name: str
    value: Decimal
    unit: str


@dataclass(kw_only=True, frozen=True)
class MarketImpliedAssumptionResult:
    """Reverse Valuation SolverのTyped Outcome Contract(D0108 §10)。
    D0108自身は実際のSolverを実装しない——将来のD0110 Solverが満たす
    べき形を定義するのみ(例外的に`solve_toy_linear_reverse_valuation()`
    というToy Adapterのみが本Contractを実際に返す)。
    """

    result_id: str
    spec_id: str
    status: MarketImpliedResultStatus
    solved_values: tuple[SolvedVariable, ...]
    fixed_assumptions_echo: tuple[FixedAssumption, ...]
    reason: str | None
    computed_at: datetime
    record_hash: str

    def __post_init__(self) -> None:
        require_nonempty_str(self.result_id, label="result_id")
        require_nonempty_str(self.spec_id, label="spec_id")
        require_tz_aware(self.computed_at, label="computed_at")
        if self.status is MarketImpliedResultStatus.SUCCESS:
            if len(self.solved_values) == 0:
                raise MarketExpectationsSchemaError("status=SUCCESS の場合 solved_values は最低1件必要です")
        elif len(self.solved_values) != 0:
            raise MarketExpectationsSchemaError(
                f"status={self.status!r}(非SUCCESS)にも関わらず solved_values が設定されています"
                "(非SUCCESSはSolved Valueを一切主張してはならない)"
            )


def build_market_implied_assumption_result(
    *,
    result_id: str,
    spec: ReverseValuationSpec,
    status: MarketImpliedResultStatus,
    computed_at: datetime,
    solved_values: Sequence[SolvedVariable] = (),
    reason: str | None = None,
) -> MarketImpliedAssumptionResult:
    """`MarketImpliedAssumptionResult`を構築する唯一のEntrypoint
    (D0108 §10)。`fixed_assumptions_echo`は常に`spec.fixed_assumptions`
    をそのまま転記する(Statusを問わず、Provenanceとして固定Assumption
    を保持する、D0108 §22D)。
    """
    canonical_solved = tuple(sorted(solved_values, key=lambda v: v.name))
    payload = {
        "result_id": result_id,
        "spec_id": spec.spec_id,
        "status": status,
        "solved_values": canonical_solved,
        "fixed_assumptions_echo": spec.fixed_assumptions,
        "reason": reason,
        "computed_at": computed_at,
    }
    return MarketImpliedAssumptionResult(
        result_id=result_id,
        spec_id=spec.spec_id,
        status=status,
        solved_values=canonical_solved,
        fixed_assumptions_echo=spec.fixed_assumptions,
        reason=reason,
        computed_at=computed_at,
        record_hash=compute_record_hash(payload),
    )


@dataclass(kw_only=True, frozen=True)
class AssumptionSurfacePoint:
    """Assumption Surface上の1点(D0108 §11)。`varied_values`は
    `AssumptionSurface.varied_assumption_names`と同じ順序・長さを持つ。
    """

    varied_values: tuple[Decimal, ...]
    solved_values: tuple[SolvedVariable, ...]


@dataclass(kw_only=True, frozen=True)
class AssumptionSurface:
    """複数未知変数を単一の偽の一意解として扱わないための、明示的な
    Solution Surface/Feasible Set表現(D0108 §8/§11)。`spec.solver_mode
    != SOLUTION_SURFACE`のSpecからは構築できない(`build_assumption_
    surface()`が拒否する)。
    """

    surface_id: str
    spec_id: str
    varied_assumption_names: tuple[str, ...]
    fixed_assumptions: tuple[FixedAssumption, ...]
    observed_market_price: Decimal
    valuation_model_id: str
    valuation_model_version: str
    generated_at: datetime
    input_available_at: datetime
    points: tuple[AssumptionSurfacePoint, ...]
    record_hash: str

    def __post_init__(self) -> None:
        require_nonempty_str(self.surface_id, label="surface_id")
        require_nonempty_str(self.spec_id, label="spec_id")
        require_nonempty_str(self.valuation_model_id, label="valuation_model_id")
        require_nonempty_str(self.valuation_model_version, label="valuation_model_version")
        require_tz_aware(self.generated_at, label="generated_at")
        require_tz_aware(self.input_available_at, label="input_available_at")
        if len(self.varied_assumption_names) == 0:
            raise MarketExpectationsSchemaError("varied_assumption_names は最低1件必要です")
        for point in self.points:
            if len(point.varied_values) != len(self.varied_assumption_names):
                raise MarketExpectationsSchemaError(
                    f"AssumptionSurfacePointのvaried_values件数({len(point.varied_values)})が"
                    f"varied_assumption_namesの件数({len(self.varied_assumption_names)})と一致しません"
                )


def build_assumption_surface(
    *,
    surface_id: str,
    spec: ReverseValuationSpec,
    varied_assumption_names: Sequence[str],
    points: Sequence[AssumptionSurfacePoint],
    generated_at: datetime,
) -> AssumptionSurface:
    """`ReverseValuationSpec`から`AssumptionSurface`を構築する唯一の
    Entrypoint(D0108 §11)。

    `spec.solver_mode != SOLUTION_SURFACE`(= 未知変数が1個のみ)の
    Specからは構築を拒否する——単一未知変数の場合は`MarketImpliedAssump
    tionResult`(Scalar)を使うべきであり、Surfaceを騙る必要がない
    (D0108 §8)。D0108自身は実際のGrid値を計算しない(`points`は
    Caller/将来のD0110が計算済みの値を渡す、D0108 §11「It does not
    need to compute a real DCF grid yet」)。
    """
    if spec.solver_mode != SolverMode.SOLUTION_SURFACE:
        raise MarketExpectationsSchemaError(
            f"ReverseValuationSpec(spec_id={spec.spec_id!r}) の solver_mode は"
            f"{spec.solver_mode!r} であり、AssumptionSurfaceを構築できません"
            "(SOLUTION_SURFACEのSpecのみ対象、単一未知変数はMarketImpliedAssumptionResultを使うこと)"
        )
    payload = {
        "surface_id": surface_id,
        "spec_id": spec.spec_id,
        "varied_assumption_names": tuple(varied_assumption_names),
        "fixed_assumptions": spec.fixed_assumptions,
        "observed_market_price": spec.observed_market_price,
        "valuation_model_id": spec.valuation_model_id,
        "valuation_model_version": spec.valuation_model_version,
        "generated_at": generated_at,
        "input_available_at": spec.price_available_at,
        "points": tuple(points),
    }
    return AssumptionSurface(
        surface_id=surface_id,
        spec_id=spec.spec_id,
        varied_assumption_names=tuple(varied_assumption_names),
        fixed_assumptions=spec.fixed_assumptions,
        observed_market_price=spec.observed_market_price,
        valuation_model_id=spec.valuation_model_id,
        valuation_model_version=spec.valuation_model_version,
        generated_at=generated_at,
        input_available_at=spec.price_available_at,
        points=tuple(points),
        record_hash=compute_record_hash(payload),
    )


def solve_toy_linear_reverse_valuation(
    spec: ReverseValuationSpec,
    *,
    result_id: str,
    decision_at: datetime,
    computed_at: datetime,
) -> MarketImpliedAssumptionResult:
    """`TOY_LINEAR_V1`——Interface自体を検証するためだけの、意図的に単純
    化したLinear Toy Adapter(D0108 §20)。本番Valuation Formulaでは
    ない。

    `observed_market_price = base_price + sensitivity * solve_for_value`
    という1つの線形関係のみを仮定し、`fixed_assumptions`に`base_price`/
    `sensitivity`(いずれもToy Model固有のKey名、実在の財務指標では
    ない)が揃っている場合のみ解く。複数未知変数(`SOLUTION_SURFACE`)
    は本Adapterでは解かず常に`UNDERDETERMINED`を返す(Grid生成は
    Caller/将来のD0110の責務、D0108 §20)。
    """
    if spec.valuation_model_id != TOY_LINEAR_V1:
        return build_market_implied_assumption_result(
            result_id=result_id,
            spec=spec,
            status=MarketImpliedResultStatus.UNSUPPORTED_MODEL,
            computed_at=computed_at,
            reason=f"valuation_model_id={spec.valuation_model_id!r} はTOY_LINEAR_V1のみ対応です",
        )
    if spec.price_available_at > decision_at:
        return build_market_implied_assumption_result(
            result_id=result_id,
            spec=spec,
            status=MarketImpliedResultStatus.PIT_INVALID,
            computed_at=computed_at,
            reason=(
                f"price_available_at({spec.price_available_at.isoformat()})がdecision_at"
                f"({decision_at.isoformat()})より後です(未来の価格情報)"
            ),
        )
    if spec.solver_mode is not SolverMode.SINGLE_VARIABLE:
        return build_market_implied_assumption_result(
            result_id=result_id,
            spec=spec,
            status=MarketImpliedResultStatus.UNDERDETERMINED,
            computed_at=computed_at,
            reason="複数未知変数はToy Adapterでは解かない(AssumptionSurfaceを使うこと)",
        )
    fixed_by_name = {a.name: a.value for a in spec.fixed_assumptions}
    if "base_price" not in fixed_by_name or "sensitivity" not in fixed_by_name:
        return build_market_implied_assumption_result(
            result_id=result_id,
            spec=spec,
            status=MarketImpliedResultStatus.INVALID_SPEC,
            computed_at=computed_at,
            reason="TOY_LINEAR_V1 は fixed_assumptions に base_price/sensitivity の両方が必要です",
        )
    sensitivity = fixed_by_name["sensitivity"]
    if sensitivity == 0:
        return build_market_implied_assumption_result(
            result_id=result_id,
            spec=spec,
            status=MarketImpliedResultStatus.NO_SOLUTION,
            computed_at=computed_at,
            reason="sensitivity が0のため解が存在しません",
        )
    base_price = fixed_by_name["base_price"]
    solve_for = spec.solve_for_variables[0]
    solved_value = (spec.observed_market_price - base_price) / sensitivity
    bound_by_name = {b.name: b for b in spec.bounded_assumptions}
    bound = bound_by_name.get(solve_for.name)
    if bound is not None and not (bound.lower_bound <= solved_value <= bound.upper_bound):
        return build_market_implied_assumption_result(
            result_id=result_id,
            spec=spec,
            status=MarketImpliedResultStatus.OUT_OF_BOUNDS,
            computed_at=computed_at,
            reason=(f"solved_value({solved_value})がBoundedAssumption[{bound.lower_bound}, {bound.upper_bound}]の範囲外です"),
        )
    return build_market_implied_assumption_result(
        result_id=result_id,
        spec=spec,
        status=MarketImpliedResultStatus.SUCCESS,
        computed_at=computed_at,
        solved_values=(SolvedVariable(name=solve_for.name, value=solved_value, unit=solve_for.unit),),
    )


def raise_if_price_look_ahead(spec: ReverseValuationSpec, *, decision_at: datetime) -> None:
    """`spec.price_available_at`が`decision_at`より後の場合にFail
    Closedする、構築/Spec検証段階向けの明示的Guard(D0108 §19「No
    look-ahead price」)。`MarketImpliedAssumptionResult`の生成経路
    (`solve_toy_linear_reverse_valuation()`)自体はTyped Statusとして
    `PIT_INVALID`を返す(本関数とは独立した、呼び出し側が明示Gateとして
    使うための補助関数)。
    """
    if spec.price_available_at > decision_at:
        raise LookAheadBiasError(
            f"ReverseValuationSpec(spec_id={spec.spec_id!r}) の price_available_at"
            f"({spec.price_available_at.isoformat()})がdecision_at({decision_at.isoformat()})より後です"
        )


__all__ = [
    "TOY_LINEAR_V1",
    "AssumptionSurface",
    "AssumptionSurfacePoint",
    "BoundedAssumption",
    "FixedAssumption",
    "MarketImpliedAssumptionResult",
    "MarketImpliedResultStatus",
    "ReverseValuationSpec",
    "SolveForVariable",
    "SolvedVariable",
    "SolverMode",
    "build_assumption_surface",
    "build_market_implied_assumption_result",
    "build_reverse_valuation_spec",
    "raise_if_price_look_ahead",
    "solve_toy_linear_reverse_valuation",
]
