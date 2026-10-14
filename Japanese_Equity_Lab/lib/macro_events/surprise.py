"""Macro Surprise: Per-Dimension Typed Computation(D0110.1)。

本Moduleは`compute_macro_surprise()`——`MacroConsensusSnapshot` +
`MacroFirstRelease`の明示的な組から、**1つのDimensionについて1つの
Surprise**を計算する唯一のEntrypoint——を提供する。

## No Aggregate Surprise(D0110.1 §13/§16、最重要)

`FOMC_SURPRISE = +0.72`のような単一Opaque Scoreは一切生成しない。
1つのEventが複数のDimensionを持つ場合(例: FOMCのPOLICY_RATEと
DOT_MEDIAN)、それぞれ独立に`compute_macro_surprise()`を呼び、別々の
`MacroSurprise`Recordとして保持する——集約は将来の別Research
Hypothesisの責務であり、本Moduleはこれを一切行わない(Source Level
ASTで確認、`13_tests/test_macro_event_surprise.py`参照)。

## Consensus PIT Rule(D0110.1 §8、必須)

Surprise計算に使う`MacroConsensusSnapshot`は必ずPre-Release(発表前)
である必要がある: `consensus_snapshot_at < actual_public_at`かつ
`consensus.available_at <= actual_public_at`。発表後にしか利用不能
だったConsensus Snapshotを過去のSurprise計算に使うことは一切しない
(Fail Closed、PIT_INVALID)。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from lib.evaluation.integrity import compute_record_hash
from lib.macro_events.model import (
    SUPPORTED_EVENT_TYPES,
    UNIT_BASIS_POINT,
    UNIT_PERCENT,
    UNIT_PERCENTAGE_POINT,
    MacroConsensusSnapshot,
    MacroEvent,
    MacroEventSchemaError,
    MacroFirstRelease,
    require_nonempty_str,
    require_tz_aware,
)

CALC_RULE_ACTUAL_MINUS_EXPECTED_PP_V1 = "ACTUAL_MINUS_EXPECTED_PP_V1"
CALC_RULE_ACTUAL_MINUS_EXPECTED_BP_V1 = "ACTUAL_MINUS_EXPECTED_BP_V1"


@dataclass(frozen=True)
class _SurpriseCalculationRule:
    """1件のSurprise計算規則(D0110.1 §15)。`expected_input_unit`と
    異なるUnitのInputを渡された場合はFail Closed(`UNIT_MISMATCH`)
    する——暗黙のUnit変換は一切行わない(D0110.1 §17)。"""

    rule_id: str
    expected_input_unit: str
    output_unit: str
    output_multiplier: Decimal


_SURPRISE_CALCULATION_RULES: dict[str, _SurpriseCalculationRule] = {
    CALC_RULE_ACTUAL_MINUS_EXPECTED_PP_V1: _SurpriseCalculationRule(
        rule_id=CALC_RULE_ACTUAL_MINUS_EXPECTED_PP_V1,
        expected_input_unit=UNIT_PERCENT,
        output_unit=UNIT_PERCENTAGE_POINT,
        output_multiplier=Decimal(1),
    ),
    CALC_RULE_ACTUAL_MINUS_EXPECTED_BP_V1: _SurpriseCalculationRule(
        rule_id=CALC_RULE_ACTUAL_MINUS_EXPECTED_BP_V1,
        expected_input_unit=UNIT_PERCENT,
        output_unit=UNIT_BASIS_POINT,
        output_multiplier=Decimal(100),
    ),
}
"""唯一のSurprise計算規則Registry(D0110.1 §15)。CPI等の素朴な数値
Releaseは`_PP_V1`(Percentage Point、無変換)、政策金利等のRate
Decisionは`_BP_V1`(Basis Point、1 Percentage Point = 100bpの明示的
決定論的変換)を使う。新しいRuleを追加する場合はここへ1件追加する
のみで、Dispatch Logic自体は変更しない。"""


class MacroSurpriseStatus(StrEnum):
    """`MacroSurpriseComputationResult.status`(D0110.1 §33)。"""

    SUCCESS = "SUCCESS"
    MISSING_CONSENSUS = "MISSING_CONSENSUS"
    MISSING_FIRST_RELEASE = "MISSING_FIRST_RELEASE"
    PIT_INVALID = "PIT_INVALID"
    UNIT_MISMATCH = "UNIT_MISMATCH"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    INVALID_DIMENSION = "INVALID_DIMENSION"
    INVALID_SURPRISE_RULE = "INVALID_SURPRISE_RULE"
    UNSUPPORTED_EVENT_TYPE = "UNSUPPORTED_EVENT_TYPE"


@dataclass(kw_only=True, frozen=True)
class MacroSurprise:
    """1つのEvent・1つのDimensionについての、1組のConsensus
    Snapshot + First Releaseから計算されたSurprise(D0110.1 §14)。
    使用した正確な`consensus_snapshot_id`/`first_release_id`を常に
    参照する——後から「最新利用可能だったConsensus」として再構成する
    ことはしない(D0110.1 §9/§14)。
    """

    surprise_id: str
    event_id: str
    dimension: str
    consensus_snapshot_id: str
    first_release_id: str
    expected_value: Decimal
    actual_value: Decimal
    surprise_value: Decimal
    surprise_unit: str
    calculation_rule_id: str
    calculated_at: datetime
    available_at: datetime
    record_hash: str

    def __post_init__(self) -> None:
        for name, value in (
            ("surprise_id", self.surprise_id),
            ("event_id", self.event_id),
            ("dimension", self.dimension),
            ("consensus_snapshot_id", self.consensus_snapshot_id),
            ("first_release_id", self.first_release_id),
            ("surprise_unit", self.surprise_unit),
            ("calculation_rule_id", self.calculation_rule_id),
        ):
            require_nonempty_str(value, label=name)
        require_tz_aware(self.calculated_at, label="calculated_at")
        require_tz_aware(self.available_at, label="available_at")


@dataclass(kw_only=True, frozen=True)
class MacroSurpriseComputationResult:
    """`compute_macro_surprise()`のTyped Outcome(D0110.1 §33)。
    `status != SUCCESS`の場合`surprise`は`None`のまま。
    """

    status: MacroSurpriseStatus
    surprise: MacroSurprise | None
    reason: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.status, MacroSurpriseStatus):
            raise MacroEventSchemaError(f"status は MacroSurpriseStatus である必要があります: {self.status!r}")
        if self.status is MacroSurpriseStatus.SUCCESS:
            if self.surprise is None:
                raise MacroEventSchemaError("status=SUCCESS の場合 surprise は必須です")
        elif self.surprise is not None:
            raise MacroEventSchemaError(f"status={self.status!r}(非SUCCESS)にも関わらず surprise が設定されています")


def _fail(status: MacroSurpriseStatus, reason: str) -> MacroSurpriseComputationResult:
    return MacroSurpriseComputationResult(status=status, surprise=None, reason=reason)


def compute_macro_surprise(
    *,
    surprise_id: str,
    event: MacroEvent,
    consensus: MacroConsensusSnapshot | None,
    first_release: MacroFirstRelease | None,
    calculation_rule_id: str,
    calculated_at: datetime,
    decision_at: datetime | None = None,
) -> MacroSurpriseComputationResult:
    """1つのEvent・1つのDimensionについてのMacroSurpriseを計算する
    唯一のEntrypoint(D0110.1 §14/§15)。

    判定順序:
    1. `event.event_type`が`SUPPORTED_EVENT_TYPES`に属すること
       (`UNSUPPORTED_EVENT_TYPE`)。
    2. `consensus`/`first_release`がいずれも提供されていること
       (`MISSING_CONSENSUS`/`MISSING_FIRST_RELEASE`)。
    3. `consensus.event_id`/`first_release.event_id`が`event.
       event_id`と一致すること(`IDENTITY_MISMATCH`)。
    4. `consensus.dimension == first_release.dimension`であること
       (`INVALID_DIMENSION`)。
    5. `calculation_rule_id`が既知のRuleであり、`consensus.unit`/
       `first_release.unit`いずれも`rule.expected_input_unit`と
       一致すること(`INVALID_SURPRISE_RULE`/`UNIT_MISMATCH`)。
    6. Consensus PIT Rule(D0110.1 §8): `consensus.consensus_
       snapshot_at < first_release.actual_public_at`かつ
       `consensus.available_at <= first_release.actual_public_at`
       であること(`PIT_INVALID`)。
    7. `decision_at`が指定された場合、`first_release.available_at`/
       `consensus.available_at`がこれより後でないこと(未来情報の
       漏洩防止、`PIT_INVALID`)。
    """
    if event.event_type not in SUPPORTED_EVENT_TYPES:
        return _fail(
            MacroSurpriseStatus.UNSUPPORTED_EVENT_TYPE,
            f"event_type={event.event_type!r} は未対応です(SUPPORTED_EVENT_TYPES={sorted(SUPPORTED_EVENT_TYPES)})",
        )
    if consensus is None:
        return _fail(MacroSurpriseStatus.MISSING_CONSENSUS, "consensus(MacroConsensusSnapshot)が指定されていません")
    if first_release is None:
        return _fail(MacroSurpriseStatus.MISSING_FIRST_RELEASE, "first_release(MacroFirstRelease)が指定されていません")

    if consensus.event_id != event.event_id:
        return _fail(
            MacroSurpriseStatus.IDENTITY_MISMATCH,
            f"consensus.event_id({consensus.event_id!r})がevent.event_id({event.event_id!r})と一致しません",
        )
    if first_release.event_id != event.event_id:
        return _fail(
            MacroSurpriseStatus.IDENTITY_MISMATCH,
            f"first_release.event_id({first_release.event_id!r})がevent.event_id({event.event_id!r})と一致しません",
        )
    if consensus.dimension != first_release.dimension:
        return _fail(
            MacroSurpriseStatus.INVALID_DIMENSION,
            f"consensus.dimension({consensus.dimension!r})がfirst_release.dimension({first_release.dimension!r})と一致しません",
        )

    rule = _SURPRISE_CALCULATION_RULES.get(calculation_rule_id)
    if rule is None:
        return _fail(
            MacroSurpriseStatus.INVALID_SURPRISE_RULE,
            f"calculation_rule_id={calculation_rule_id!r} は未知のRuleです(既知: {sorted(_SURPRISE_CALCULATION_RULES)})",
        )
    if consensus.unit != rule.expected_input_unit:
        return _fail(
            MacroSurpriseStatus.UNIT_MISMATCH,
            f"consensus.unit({consensus.unit!r})がRule期待Unit({rule.expected_input_unit!r})と一致しません",
        )
    if first_release.unit != rule.expected_input_unit:
        return _fail(
            MacroSurpriseStatus.UNIT_MISMATCH,
            f"first_release.unit({first_release.unit!r})がRule期待Unit({rule.expected_input_unit!r})と一致しません",
        )

    if consensus.consensus_snapshot_at >= first_release.actual_public_at:
        return _fail(
            MacroSurpriseStatus.PIT_INVALID,
            f"consensus.consensus_snapshot_at({consensus.consensus_snapshot_at.isoformat()})が"
            f"first_release.actual_public_at({first_release.actual_public_at.isoformat()})以降です"
            "(発表後のConsensusはPre-Release Surpriseに使えません)",
        )
    if consensus.available_at > first_release.actual_public_at:
        return _fail(
            MacroSurpriseStatus.PIT_INVALID,
            f"consensus.available_at({consensus.available_at.isoformat()})が"
            f"first_release.actual_public_at({first_release.actual_public_at.isoformat()})より後です"
            "(発表前に観測されたConsensusでも、発表後にしか利用可能でなかった場合は使えません)",
        )

    if decision_at is not None:
        if first_release.available_at > decision_at:
            return _fail(
                MacroSurpriseStatus.PIT_INVALID,
                f"first_release.available_at({first_release.available_at.isoformat()})が"
                f"decision_at({decision_at.isoformat()})より後です(未来の発表情報)",
            )
        if consensus.available_at > decision_at:
            return _fail(
                MacroSurpriseStatus.PIT_INVALID,
                f"consensus.available_at({consensus.available_at.isoformat()})が"
                f"decision_at({decision_at.isoformat()})より後です(未来のConsensus情報)",
            )

    surprise_value = (first_release.actual_first_release - consensus.value) * rule.output_multiplier
    available_at = max(consensus.available_at, first_release.available_at)
    payload = {
        "surprise_id": surprise_id,
        "event_id": event.event_id,
        "dimension": consensus.dimension,
        "consensus_snapshot_id": consensus.consensus_snapshot_id,
        "first_release_id": first_release.release_id,
        "expected_value": consensus.value,
        "actual_value": first_release.actual_first_release,
        "surprise_value": surprise_value,
        "surprise_unit": rule.output_unit,
        "calculation_rule_id": calculation_rule_id,
        "calculated_at": calculated_at,
        "available_at": available_at,
    }
    surprise = MacroSurprise(
        surprise_id=surprise_id,
        event_id=event.event_id,
        dimension=consensus.dimension,
        consensus_snapshot_id=consensus.consensus_snapshot_id,
        first_release_id=first_release.release_id,
        expected_value=consensus.value,
        actual_value=first_release.actual_first_release,
        surprise_value=surprise_value,
        surprise_unit=rule.output_unit,
        calculation_rule_id=calculation_rule_id,
        calculated_at=calculated_at,
        available_at=available_at,
        record_hash=compute_record_hash(payload),
    )
    return MacroSurpriseComputationResult(status=MacroSurpriseStatus.SUCCESS, surprise=surprise, reason=None)


__all__ = [
    "CALC_RULE_ACTUAL_MINUS_EXPECTED_BP_V1",
    "CALC_RULE_ACTUAL_MINUS_EXPECTED_PP_V1",
    "MacroSurprise",
    "MacroSurpriseComputationResult",
    "MacroSurpriseStatus",
    "compute_macro_surprise",
]
