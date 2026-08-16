"""Hypothesis Registry の中心的schema。

LOCKED以降は内容(terms)のSHA-256 hashを保存し、コードレベルで書き換えを禁止する。
条件を変更する場合は元のHypothesisを書き換えず、新しいHypothesis IDを発行し
parent_hypothesis_idで系譜を残す(lock() / with_status() / revise() 参照)。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum

from lib.errors import HypothesisImmutabilityError
from lib.schemas.base import RecordMeta

_TERMS_FIELDS = (
    "claim",
    "mechanism",
    "universe",
    "signal_definition",
    "entry_rule",
    "exit_rule",
    "holding_period",
    "benchmark",
    "success_metric",
    "failure_metric",
    "required_data",
)


class HypothesisStatus(StrEnum):
    DRAFT = "DRAFT"
    LOCKED = "LOCKED"
    TESTED = "TESTED"
    REJECTED = "REJECTED"
    PAPER = "PAPER"
    VALIDATED = "VALIDATED"


@dataclass(kw_only=True, frozen=True)
class Hypothesis(RecordMeta):
    hypothesis_id: str
    source_idea_id: str | None
    claim: str
    mechanism: str
    universe: str
    signal_definition: str
    entry_rule: str
    exit_rule: str
    holding_period: str
    success_metric: str
    failure_metric: str
    benchmark: str = "TOPIX"
    required_data: tuple[str, ...] = field(default_factory=tuple)
    status: HypothesisStatus = HypothesisStatus.DRAFT
    locked_terms_hash: str | None = None
    parent_hypothesis_id: str | None = None

    def terms_hash(self) -> str:
        """LOCK対象となる条件(terms)フィールドのみのcanonical hash。"""
        payload = {name: getattr(self, name) for name in _TERMS_FIELDS}
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def lock(self) -> Hypothesis:
        """DRAFT -> LOCKEDに遷移し、現在のtermsのhashを保存する。"""
        if self.status != HypothesisStatus.DRAFT:
            raise HypothesisImmutabilityError(f"DRAFT以外(現在: {self.status})からはlockできません")
        return replace(
            self,
            status=HypothesisStatus.LOCKED,
            locked_terms_hash=self.terms_hash(),
            updated_at=datetime.now(UTC),
        )

    def with_status(self, new_status: HypothesisStatus) -> Hypothesis:
        """termsを変えずにライフサイクルのstatusだけを進める(LOCKED -> TESTED等)。"""
        if self.status == HypothesisStatus.DRAFT:
            raise HypothesisImmutabilityError("DRAFTのHypothesisはまずlock()してください")
        if self.locked_terms_hash is not None and self.terms_hash() != self.locked_terms_hash:
            raise HypothesisImmutabilityError("LOCKED後にtermsが変更されています(改ざん検知)")
        return replace(self, status=new_status, updated_at=datetime.now(UTC))

    def revise(self, *, new_hypothesis_id: str, **term_changes: object) -> Hypothesis:
        """LOCKED以降のHypothesisを直接書き換えず、新しいIDで派生版を作る。"""
        if self.status == HypothesisStatus.DRAFT:
            raise HypothesisImmutabilityError("DRAFTのHypothesisはreviseせず直接変更してください")
        unknown = set(term_changes) - set(_TERMS_FIELDS)
        if unknown:
            raise ValueError(f"terms以外のフィールドはreviseできません: {unknown}")
        return replace(
            self,
            hypothesis_id=new_hypothesis_id,
            parent_hypothesis_id=self.hypothesis_id,
            status=HypothesisStatus.DRAFT,
            locked_terms_hash=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            **term_changes,
        )
