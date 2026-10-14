"""Reverse Valuation: Generic Bisection Solver over the SAME Model
(D0110)。

本Moduleは`lib.valuation.engine`の`compute_enterprise_value()`/
`compute_equity_value()`/`compute_value_per_share()`を**そのまま**
呼ぶ——Forward専用の別Formulaを複製しない(D0110 §2/§10)。既存D0108
`lib.expectations.reverse_spec`のContract(`ReverseValuationSpec`/
`MarketImpliedAssumptionResult`/`AssumptionSurface`)をそのまま再利用
し、新しいMarket-Implied Expectation Formatは作らない(D0110 §24)。

## Monotonicity(D0110 §14、本Model固有の保証)

`EquityValue/ShareCount`は以下の4変数いずれについても、他3変数を固定
した場合に単調である(本Model——`EnterpriseValue = OperatingIncome ×
Multiple`、`EquityValue = EnterpriseValue - NetDebt`、`ValuePerShare =
EquityValue / ShareCount`——が各変数について線形/反比例であることに
よる、Generic Solverに対する一般的な保証ではない):

- `OPERATING_INCOME`: `Multiple > 0`(Model制約)の下で単調増加。
- `EV_OPERATING_INCOME_MULTIPLE`: `OperatingIncome`の符号方向に単調
  (`OperatingIncome = 0`の場合は定数、退化Caseとして検出する)。
- `NET_DEBT`: 常に単調減少。
- `SHARE_COUNT`: `EquityValue`の符号方向に単調(`EquityValue = 0`の
  場合は定数、退化Caseとして検出する)。

本Solverは上記の解析的な方向を仮定せず、`f(lower_bound)`/`f(upper_
bound)`を実際に評価して経験的に方向を判定する(Model-specific
Shortcutではなく、Genericな境界評価のみに依拠する、D0110 §5)。
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

from lib.expectations.model import require_tz_aware
from lib.expectations.reverse_spec import (
    AssumptionSurface,
    AssumptionSurfacePoint,
    FixedAssumption,
    MarketImpliedAssumptionResult,
    MarketImpliedResultStatus,
    ReverseValuationSpec,
    SolvedVariable,
    SolverMode,
    build_assumption_surface,
    build_market_implied_assumption_result,
    build_reverse_valuation_spec,
)
from lib.valuation.engine import compute_enterprise_value, compute_equity_value, compute_value_per_share
from lib.valuation.forward_reverse_model import (
    SUPPORTED_SOLVE_VARIABLES,
    VALUATION_MODEL_ID,
    VARIABLE_EV_OPERATING_INCOME_MULTIPLE,
    VARIABLE_NET_DEBT,
    VARIABLE_OPERATING_INCOME,
    VARIABLE_SHARE_COUNT,
)

DEFAULT_TOLERANCE = Decimal("0.0001")
DEFAULT_MAX_ITERATIONS = 200
_POSITIVE_DOMAIN_VARIABLES = frozenset({VARIABLE_EV_OPERATING_INCOME_MULTIPLE, VARIABLE_SHARE_COUNT})


def _evaluate_model(values: dict[str, Decimal]) -> Decimal:
    """D0110の唯一のModel評価(Forward/Reverse共有、D0110 §2)。
    `lib.valuation.engine`の3つの純粋関数をそのまま呼ぶ。"""
    enterprise_value = compute_enterprise_value(
        operating_income=values[VARIABLE_OPERATING_INCOME], multiple_value=values[VARIABLE_EV_OPERATING_INCOME_MULTIPLE]
    )
    equity_value = compute_equity_value(enterprise_value=enterprise_value, net_debt=values[VARIABLE_NET_DEBT])
    return compute_value_per_share(equity_value=equity_value, share_count=values[VARIABLE_SHARE_COUNT])


def _bisect(
    *,
    fixed_values: dict[str, Decimal],
    solve_name: str,
    lower_bound: Decimal,
    upper_bound: Decimal,
    target: Decimal,
    tolerance: Decimal,
    max_iterations: int,
) -> tuple[Decimal | None, MarketImpliedResultStatus | None, str | None]:
    """`target = f(solve_name)`(他は`fixed_values`で固定)をDecimal
    Bisectionで解く。`f`の方向を経験的に判定し(D0110 §14)、
    `[lower_bound, upper_bound]`が`target`をBracketしない場合は
    `NO_SOLUTION`、縮退(`f(lo) == f(hi)`)の場合は`target`との一致
    有無で`MULTIPLE_SOLUTIONS`/`NO_SOLUTION`を返す——いずれも偽の一意
    解を返さない(D0110 §11/§13)。
    """

    def f(x: Decimal) -> Decimal:
        return _evaluate_model({**fixed_values, solve_name: x})

    f_lo = f(lower_bound)
    f_hi = f(upper_bound)

    if f_lo == f_hi:
        if f_lo == target:
            return (
                None,
                MarketImpliedResultStatus.MULTIPLE_SOLUTIONS,
                (
                    f"solve_name={solve_name!r} は[{lower_bound}, {upper_bound}]全域でf(x)={f_lo}"
                    "(定数)であり、target価格と一致するため一意解がありません"
                ),
            )
        return (
            None,
            MarketImpliedResultStatus.NO_SOLUTION,
            (
                f"solve_name={solve_name!r} は[{lower_bound}, {upper_bound}]全域でf(x)={f_lo}"
                f"(定数)であり、target({target})と一致しないため解がありません"
            ),
        )

    increasing = f_hi > f_lo
    low_value, high_value = min(f_lo, f_hi), max(f_lo, f_hi)
    if not (low_value <= target <= high_value):
        return (
            None,
            MarketImpliedResultStatus.NO_SOLUTION,
            (
                f"target({target})が[{lower_bound}, {upper_bound}]の範囲で取りうる値"
                f"[{low_value}, {high_value}]の外側です(Bounds内に解がありません)"
            ),
        )

    lo, hi = lower_bound, upper_bound
    for _ in range(max_iterations):
        mid = (lo + hi) / Decimal(2)
        f_mid = f(mid)
        if abs(f_mid - target) <= tolerance:
            return mid, None, None
        if (f_mid < target) == increasing:
            lo = mid
        else:
            hi = mid
        if hi == lo:
            # Decimal有効桁数の限界でlo/hiがこれ以上分離できない
            # (Domain Widthのtolerance Breakではない——Function-Value
            # Toleranceとの単位混同を避けるため、Domain基準での早期
            # Breakは行わない。単にこれ以上縮小できないことのみ検出)。
            break

    final_mid = (lo + hi) / Decimal(2)
    if abs(f(final_mid) - target) <= tolerance:
        return final_mid, None, None
    return (
        None,
        MarketImpliedResultStatus.NO_SOLUTION,
        (f"max_iterations({max_iterations})に到達してもtolerance({tolerance})以内に収束しませんでした"),
    )


def solve_reverse_valuation(
    spec: ReverseValuationSpec,
    *,
    result_id: str,
    decision_at: datetime,
    computed_at: datetime,
    tolerance: Decimal = DEFAULT_TOLERANCE,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
) -> MarketImpliedAssumptionResult:
    """`VALUATION_MODEL_ID`(`EV_OPERATING_INCOME_MULTIPLE_V1`)に対する
    唯一のReverse Solver Entrypoint(D0110 §10)。`OPERATING_INCOME`/
    `EV_OPERATING_INCOME_MULTIPLE`/`NET_DEBT`/`SHARE_COUNT`のいずれか
    1つを未知変数として解く(他3つは`fixed_assumptions`で固定)。

    `lib.valuation.engine.evaluate_forward_valuation()`と**同じ3つの
    純粋関数**(`_evaluate_model()`経由)を呼ぶ——Forward/Reverseが
    異なる数式を使うことを構造的に防ぐ(D0110 §2、Reviewer Focus #1)。
    """
    require_tz_aware(decision_at, label="decision_at")
    require_tz_aware(computed_at, label="computed_at")
    if spec.valuation_model_id != VALUATION_MODEL_ID:
        return build_market_implied_assumption_result(
            result_id=result_id,
            spec=spec,
            status=MarketImpliedResultStatus.UNSUPPORTED_MODEL,
            computed_at=computed_at,
            reason=f"valuation_model_id={spec.valuation_model_id!r} は{VALUATION_MODEL_ID!r}のみ対応です",
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
            reason="複数未知変数は本Scalar Solverでは解かない(compute_assumption_surface_for_valuation()を使うこと)",
        )

    solve_for = spec.solve_for_variables[0]
    if solve_for.name not in SUPPORTED_SOLVE_VARIABLES:
        return build_market_implied_assumption_result(
            result_id=result_id,
            spec=spec,
            status=MarketImpliedResultStatus.INVALID_SPEC,
            computed_at=computed_at,
            reason=f"solve_for_variables[0].name={solve_for.name!r} は{sorted(SUPPORTED_SOLVE_VARIABLES)}のいずれでもありません",
        )

    fixed_by_name = {a.name: a.value for a in spec.fixed_assumptions}
    required_fixed = SUPPORTED_SOLVE_VARIABLES - {solve_for.name}
    missing_fixed = required_fixed - fixed_by_name.keys()
    if missing_fixed:
        return build_market_implied_assumption_result(
            result_id=result_id,
            spec=spec,
            status=MarketImpliedResultStatus.INVALID_SPEC,
            computed_at=computed_at,
            reason=f"fixed_assumptionsに必要な変数が不足しています: {sorted(missing_fixed)}",
        )

    for positive_name in _POSITIVE_DOMAIN_VARIABLES & fixed_by_name.keys():
        if fixed_by_name[positive_name] <= 0:
            return build_market_implied_assumption_result(
                result_id=result_id,
                spec=spec,
                status=MarketImpliedResultStatus.INVALID_SPEC,
                computed_at=computed_at,
                reason=f"fixed_assumptions[{positive_name!r}]={fixed_by_name[positive_name]}は0以下です"
                f"({VALUATION_MODEL_ID}では正の値が必要)",
            )

    bound_by_name = {b.name: b for b in spec.bounded_assumptions}
    bound = bound_by_name.get(solve_for.name)
    if bound is None:
        return build_market_implied_assumption_result(
            result_id=result_id,
            spec=spec,
            status=MarketImpliedResultStatus.INVALID_SPEC,
            computed_at=computed_at,
            reason=f"solve_for_variables[0].name={solve_for.name!r} に対応するbounded_assumptionsがありません",
        )
    if solve_for.name in _POSITIVE_DOMAIN_VARIABLES and bound.lower_bound <= 0:
        return build_market_implied_assumption_result(
            result_id=result_id,
            spec=spec,
            status=MarketImpliedResultStatus.INVALID_SPEC,
            computed_at=computed_at,
            reason=f"solve_for_variables[0].name={solve_for.name!r} のlower_bound({bound.lower_bound})は0以下です"
            f"({VALUATION_MODEL_ID}では正の値が必要)",
        )

    solved_value, failure_status, failure_reason = _bisect(
        fixed_values=fixed_by_name,
        solve_name=solve_for.name,
        lower_bound=bound.lower_bound,
        upper_bound=bound.upper_bound,
        target=spec.observed_market_price,
        tolerance=tolerance,
        max_iterations=max_iterations,
    )
    if failure_status is not None:
        assert failure_reason is not None
        return build_market_implied_assumption_result(
            result_id=result_id, spec=spec, status=failure_status, computed_at=computed_at, reason=failure_reason
        )
    assert solved_value is not None
    return build_market_implied_assumption_result(
        result_id=result_id,
        spec=spec,
        status=MarketImpliedResultStatus.SUCCESS,
        computed_at=computed_at,
        solved_values=(SolvedVariable(name=solve_for.name, value=solved_value, unit=solve_for.unit),),
        # Solver Tolerance/Precision Policyを明示的に記録する(D0110 §31
        # 「No False Precision...Record solver tolerance」)。SUCCESSでも
        # reasonはErrorを意味しない(D0108 MarketImpliedAssumptionResult
        # のreasonはStatusに関わらず設定可能)。
        reason=f"bisection_tolerance={tolerance}",
    )


def compute_assumption_surface_for_valuation(
    spec: ReverseValuationSpec,
    *,
    surface_id: str,
    varied_variable: str,
    varied_values: Sequence[Decimal],
    decision_at: datetime,
    generated_at: datetime,
    tolerance: Decimal = DEFAULT_TOLERANCE,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
) -> AssumptionSurface:
    """2未知変数の`ReverseValuationSpec`(`solver_mode=SOLUTION_
    SURFACE`)について、`varied_variable`を明示的なGrid値で走査し、
    残り1変数を各Grid点で`solve_reverse_valuation()`(SAME Model、
    SAME Bisection)により解く、唯一のProduction Surface計算
    Entrypoint(D0110 §12)。

    解けなかったGrid点(`status != SUCCESS`)は`points`に含めない
    (存在しない解をInterpolationで補完しない、D0110 §12「No
    interpolation presented as fact unless explicit」)。
    """
    require_tz_aware(generated_at, label="generated_at")
    if spec.solver_mode is not SolverMode.SOLUTION_SURFACE:
        raise ValueError(
            f"ReverseValuationSpec(spec_id={spec.spec_id!r}) の solver_mode は{spec.solver_mode!r}であり、"
            "AssumptionSurfaceを計算できません(SOLUTION_SURFACEのSpecのみ対象)"
        )
    if len(spec.solve_for_variables) != 2:
        raise ValueError(
            f"compute_assumption_surface_for_valuation()は2未知変数のSpecのみ対応します(実際: {len(spec.solve_for_variables)}件)"
        )
    solve_for_names = {v.name for v in spec.solve_for_variables}
    if varied_variable not in solve_for_names:
        raise ValueError(f"varied_variable={varied_variable!r} はspec.solve_for_variablesに含まれません")
    varied_unit = next(v.unit for v in spec.solve_for_variables if v.name == varied_variable)
    remaining = next(v for v in spec.solve_for_variables if v.name != varied_variable)

    # 構造的な誤設定(Model不一致・未来価格・remaining変数のBound欠落)
    # は、各Grid点が個別にFailして「全点失敗 = 空のPoints」へ埋没する
    # 前に、ここで一度だけ明示的にRaiseする——構造的誤設定による空
    # Surfaceと、経済的に正当な「Grid全域で解無し」を区別する
    # (/code-review high Finding、「No interpolation presented as
    # fact」原則を空Surface自体にも適用する)。
    if spec.valuation_model_id != VALUATION_MODEL_ID:
        raise ValueError(f"valuation_model_id={spec.valuation_model_id!r} は{VALUATION_MODEL_ID!r}のみ対応です")
    if spec.price_available_at > decision_at:
        raise ValueError(
            f"price_available_at({spec.price_available_at.isoformat()})がdecision_at"
            f"({decision_at.isoformat()})より後です(未来の価格情報)"
        )
    bound_by_name = {b.name: b for b in spec.bounded_assumptions}
    if remaining.name not in bound_by_name:
        raise ValueError(f"remaining変数={remaining.name!r} に対応するbounded_assumptionsがありません")

    points = []
    for idx, value in enumerate(varied_values):
        point_spec = build_reverse_valuation_spec(
            spec_id=f"{spec.spec_id}::POINT_{idx}",
            valuation_model_id=spec.valuation_model_id,
            valuation_model_version=spec.valuation_model_version,
            entity_id=spec.entity_id,
            observed_market_price=spec.observed_market_price,
            price_currency=spec.price_currency,
            price_observed_at=spec.price_observed_at,
            price_available_at=spec.price_available_at,
            price_source_id=spec.price_source_id,
            solve_for_variables=(remaining,),
            valuation_horizon=spec.valuation_horizon,
            created_at=generated_at,
            fixed_assumptions=(*spec.fixed_assumptions, FixedAssumption(name=varied_variable, value=value, unit=varied_unit)),
            bounded_assumptions=spec.bounded_assumptions,
        )
        point_result = solve_reverse_valuation(
            point_spec,
            result_id=f"{surface_id}_POINT_{idx}",
            decision_at=decision_at,
            computed_at=generated_at,
            tolerance=tolerance,
            max_iterations=max_iterations,
        )
        if point_result.status is MarketImpliedResultStatus.SUCCESS:
            points.append(AssumptionSurfacePoint(varied_values=(value,), solved_values=point_result.solved_values))

    return build_assumption_surface(
        surface_id=surface_id,
        spec=spec,
        varied_assumption_names=(varied_variable,),
        points=tuple(points),
        generated_at=generated_at,
    )


__all__ = [
    "DEFAULT_MAX_ITERATIONS",
    "DEFAULT_TOLERANCE",
    "compute_assumption_surface_for_valuation",
    "solve_reverse_valuation",
]
