"""Phase5 v1: Hypothesis Preregistration。

**目的の再確認**: 「儲かる戦略を発見すること」ではなく「仮説を事前登録し、
PIT-safeなDataset Contractを固定し、Train/Validation/Locked Testを
分離し、1つの単純な仮説をEnd-to-Endで検証する」こと(Phase5 v1要件§1)。
Resultを見てからPreregistrationを書き換えない、という原則をCode上で
強制する(既存`lib.schemas.hypothesis.Hypothesis`のLOCK-based Immutability
Patternをそのまま踏襲、新規のImmutability機構は発明しない)。

## 既存`Hypothesis`との関係(Fork/複製ではなく参照)

`Hypothesis`(`lib.schemas.hypothesis`)は既にclaim/mechanism/entry_rule/
exit_rule/benchmark等の「戦略の中身」をLOCK可能な形で保持している。
`Preregistration`はこれを複製せず`hypothesis_id`で参照し、Phase5固有の
追加要件(Research Question・Alternative Explanations・Falsification
Condition・Train/Validation/Locked Test期間・Primary/Secondary Metric・
Allowed Adjustments・Forbidden Capabilities)のみを追加で固定する。

## Train -> Validation -> Locked Testの時系列非重複

`__post_init__`で3期間がChronological(Train終了 < Validation開始、
Validation終了 < Locked Test開始)であることを構造的に強制する
(Random Split禁止、Phase5 v1要件§19)。

## Immutability

`DRAFT`のみ`preregister()`でFieldを固定できる(Coreとなる全Fieldの
SHA-256 Hashを`locked_core_hash`へ保存)。`PREREGISTERED`後にCore Field
を書き換えようとすると`PreregistrationImmutabilityError`。変更したい
場合は`revise()`で新しい`preregistration_id`を発行し、
`parent_preregistration_id`で系譜を残す(Silent Overwrite禁止、
Phase5 v1要件§43)。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from enum import StrEnum

from lib.errors import PreregistrationImmutabilityError
from lib.schemas.base import RecordMeta

# Phase5 v1で使用禁止のData Capability(D0061 Phase5 v1 Forbidden Data)。
# Preregistration自体がこの一覧を保持することで、将来Runnerがこれ以外の
# CapabilityをImportしていないかのStructural Testが同じ一覧を参照できる。
DEFAULT_FORBIDDEN_CAPABILITIES: tuple[str, ...] = (
    "lib.fundamentals",
    "lib.disclosures",
    "lib.positioning",
    "lib.macro",
    "lib.global_market",
    "lib.news",
    "lib.consensus",
    "lib.evidence",
)

_CORE_FIELDS = (
    "hypothesis_id",
    "research_question",
    "alternative_explanations",
    "falsification_condition",
    "dataset_contract_id",
    "universe_definition",
    "train_period_start",
    "train_period_end",
    "validation_period_start",
    "validation_period_end",
    "locked_test_period_start",
    "locked_test_period_end",
    "primary_metric",
    "secondary_metrics",
    "benchmark",
    "parameters",
    "allowed_adjustments",
    "forbidden_capabilities",
)


class PreregistrationStatus(StrEnum):
    DRAFT = "DRAFT"
    PREREGISTERED = "PREREGISTERED"


@dataclass(kw_only=True, frozen=True)
class Preregistration(RecordMeta):
    """1 Hypothesisの検証手順を事前固定する記録。"""

    preregistration_id: str
    hypothesis_id: str
    research_question: str
    alternative_explanations: tuple[str, ...]
    falsification_condition: str
    dataset_contract_id: str
    universe_definition: str
    train_period_start: date
    train_period_end: date
    validation_period_start: date
    validation_period_end: date
    locked_test_period_start: date
    locked_test_period_end: date
    primary_metric: str
    secondary_metrics: tuple[str, ...] = field(default_factory=tuple)
    benchmark: str = "TOPIX"
    parameters: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    allowed_adjustments: tuple[str, ...] = field(default_factory=tuple)
    forbidden_capabilities: tuple[str, ...] = DEFAULT_FORBIDDEN_CAPABILITIES
    status: PreregistrationStatus = PreregistrationStatus.DRAFT
    locked_core_hash: str | None = None
    parent_preregistration_id: str | None = None

    def __post_init__(self) -> None:
        if not self.preregistration_id:
            raise ValueError("preregistration_id は空にできません")
        if not self.hypothesis_id:
            raise ValueError("hypothesis_id は空にできません")
        if len(self.alternative_explanations) < 2:
            raise ValueError("alternative_explanations は最低2つ必要です(Phase5 v1要件§31)")
        if not self.falsification_condition:
            raise ValueError("falsification_condition は空にできません(Phase5 v1要件§32)")
        if self.train_period_start > self.train_period_end:
            raise ValueError("train_period_start は train_period_end 以前である必要があります")
        if self.validation_period_start > self.validation_period_end:
            raise ValueError("validation_period_start は validation_period_end 以前である必要があります")
        if self.locked_test_period_start > self.locked_test_period_end:
            raise ValueError("locked_test_period_start は locked_test_period_end 以前である必要があります")
        if self.train_period_end >= self.validation_period_start:
            raise ValueError("Train期間とValidation期間が時系列で重複/逆転しています(Random Split禁止、Phase5 v1要件§19)")
        if self.validation_period_end >= self.locked_test_period_start:
            raise ValueError("Validation期間とLocked Test期間が時系列で重複/逆転しています(Random Split禁止、Phase5 v1要件§19)")

    def core_terms(self) -> dict[str, object]:
        return {name: getattr(self, name) for name in _CORE_FIELDS}

    def core_hash(self) -> str:
        canonical = json.dumps(self.core_terms(), sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def preregister(self) -> Preregistration:
        """DRAFT -> PREREGISTEREDへ遷移し、現在のCore Fieldsのhashを保存する。"""
        if self.status != PreregistrationStatus.DRAFT:
            raise PreregistrationImmutabilityError(f"DRAFT以外(現在: {self.status})からはpreregisterできません")
        return replace(
            self,
            status=PreregistrationStatus.PREREGISTERED,
            locked_core_hash=self.core_hash(),
            updated_at=datetime.now(UTC),
        )

    def assert_not_mutated(self) -> None:
        """PREREGISTERED以降、Core Fieldsが実際に変わっていないことを確認する
        (改ざん検知、`Hypothesis.with_status()`と同じPattern)。"""
        if self.status == PreregistrationStatus.DRAFT:
            raise PreregistrationImmutabilityError("DRAFTのPreregistrationはまずpreregister()してください")
        if self.locked_core_hash is not None and self.core_hash() != self.locked_core_hash:
            raise PreregistrationImmutabilityError("PREREGISTERED後にCore Fieldsが変更されています(改ざん検知)")

    def revise(self, *, new_preregistration_id: str, **term_changes: object) -> Preregistration:
        """PREREGISTERED以降のPreregistrationを直接書き換えず、新しいIDで派生版を
        作る(Result後の無断書き換え禁止、Phase5 v1要件§43)。"""
        if self.status == PreregistrationStatus.DRAFT:
            raise PreregistrationImmutabilityError("DRAFTのPreregistrationはreviseせず直接変更してください")
        unknown = set(term_changes) - set(_CORE_FIELDS)
        if unknown:
            raise ValueError(f"Core Fields以外はreviseできません: {unknown}")
        return replace(
            self,
            preregistration_id=new_preregistration_id,
            parent_preregistration_id=self.preregistration_id,
            status=PreregistrationStatus.DRAFT,
            locked_core_hash=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            **term_changes,  # type: ignore[arg-type]
        )


__all__ = [
    "DEFAULT_FORBIDDEN_CAPABILITIES",
    "Preregistration",
    "PreregistrationStatus",
]
