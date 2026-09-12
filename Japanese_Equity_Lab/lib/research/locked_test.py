"""Phase5 v1: Locked Test隔離。

RESEARCH_RULES.md「Hidden Test隔離(Phase5必須要件、D0042)」が既に
Roadmapとして明記していたAccess段階をそのまま実装する:

```
RESEARCH -> VALIDATION -> LOCKED_TEST -> FUTURE / PAPER_TRADE
```

Promptで「見ないでください」と指示するだけでは不十分であり、Dataset Access
Layer自体で隔離する必要がある、というRESEARCH_RULES.mdの指摘に対応するため、
`LockedTestGate`はUnlockするまで`unlock()`を呼んだ形跡(`LockedTestAuditRecord`)
を残させ、一度Unlockした後の再Unlockを`LockedTestAccessError`で拒否する
(一度見たLocked Testは、以後純粋なHidden Testとして再利用しない、
「燃え尽きた期間」と同じ趣旨をStructuralに強制する)。

このLabは個人用ローカル実行であり、完全なSecurity Boundary(OS権限分離等)
は要求しない。「通常のAPI経由ではLocked Test結果を誤って取得できない」
という誤操作防止レベルのStructural Gateで十分(Phase5 v1要件§61)。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from lib.errors import LockedTestAccessError


class LockedTestGateProtocol(Protocol):
    """`LockedTestGate`/`FileBackedLockedTestGate`共通のRunner向けInterface。

    Runner(`lib.research.runner.run_split`)はUnlock方法(メモリのみ/File永続化)
    を意識せず、`assert_unlocked()`だけを呼べればよい。
    """

    def assert_unlocked(self, experiment_id: str) -> None: ...


class AccessStage(StrEnum):
    """RESEARCH_RULES.md「Hidden Test隔離」が定めるAccess段階。"""

    RESEARCH = "RESEARCH"
    VALIDATION = "VALIDATION"
    LOCKED_TEST = "LOCKED_TEST"
    FUTURE_PAPER_TRADE = "FUTURE_PAPER_TRADE"


@dataclass(kw_only=True, frozen=True)
class LockedTestAuditRecord:
    """Locked Testに対する1回のUnlock操作の監査記録(§45)。"""

    experiment_id: str
    reason: str
    actor: str
    unlocked_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class LockedTestGate:
    """Experiment単位でLocked Testへのアクセスを一度だけ許可するGate。

    `unlock()`を呼ぶまで`is_unlocked()`はFalseを返し、Runnerはこの状態を
    Locked Test splitを実行してよいかの判定に使う。一度Unlockした
    Experiment IDに対して再度`unlock()`を呼ぶと`LockedTestAccessError`
    (Knowledge Contamination防止、RESEARCH_RULES.mdの「燃え尽きた期間」と
    同じ趣旨)。
    """

    _audit_log: dict[str, LockedTestAuditRecord] = field(default_factory=dict)

    def is_unlocked(self, experiment_id: str) -> bool:
        return experiment_id in self._audit_log

    def unlock(self, *, experiment_id: str, reason: str, actor: str) -> LockedTestAuditRecord:
        if self.is_unlocked(experiment_id):
            raise LockedTestAccessError(
                f"experiment_id={experiment_id} は既にLocked TestをUnlock済みです(再Unlockは禁止、Knowledge Contamination防止)"
            )
        if not reason:
            raise ValueError("reason は空にできません(Unlock理由の記録は必須、§45)")
        if not actor:
            raise ValueError("actor は空にできません(Unlock実行者の記録は必須、§45)")
        record = LockedTestAuditRecord(experiment_id=experiment_id, reason=reason, actor=actor)
        self._audit_log[experiment_id] = record
        return record

    def assert_unlocked(self, experiment_id: str) -> None:
        """Locked Test splitを読む前にRunnerが呼ぶGate本体。"""
        if not self.is_unlocked(experiment_id):
            raise LockedTestAccessError(
                f"experiment_id={experiment_id} はLocked TestをUnlockしていません(unlock()を先に呼んでください)"
            )

    def audit_trail(self) -> tuple[LockedTestAuditRecord, ...]:
        return tuple(self._audit_log.values())

    @classmethod
    def restore(cls, records: list[LockedTestAuditRecord]) -> LockedTestGate:
        """既存のAudit Record列からGateを復元する(プロセスをまたいだUnlock状態の
        永続化に使う、`FileBackedLockedTestGate`参照)。復元時点でreason/actorの
        再検証は行わない(記録時点で既に検証済みのため)が、同一experiment_idの
        重複はAudit Trail自体の破損を意味するため拒否する。"""
        gate = cls()
        for record in records:
            if gate.is_unlocked(record.experiment_id):
                raise LockedTestAccessError(f"Audit Trailにexperiment_id={record.experiment_id} の重複Unlock記録があります(破損)")
            gate._audit_log[record.experiment_id] = record
        return gate


def _audit_record_to_dict(record: LockedTestAuditRecord) -> dict[str, Any]:
    payload = asdict(record)
    payload["unlocked_at"] = record.unlocked_at.isoformat()
    return payload


def _audit_record_from_dict(data: dict[str, Any]) -> LockedTestAuditRecord:
    d = dict(data)
    d["unlocked_at"] = datetime.fromisoformat(d["unlocked_at"])
    return LockedTestAuditRecord(**d)


class FileBackedLockedTestGate:
    """`LockedTestGate`をJSON Lines(追記専用)で永続化するWrapper。

    このLabのScriptはExperimentごとに別プロセス(別コマンド実行)として動くため、
    Unlock状態をプロセス内メモリだけに持つ`LockedTestGate`単体では、
    `--unlock`実行後の別の`--split locked_test`実行でUnlock状態が失われてしまう。
    このWrapperはUnlock操作のたびにAudit Recordを追記し、次回起動時は
    ファイルから`LockedTestGate.restore()`する。追記専用であり、既存行の
    書き換え・削除APIは提供しない(RAW-001と同じ方針)。
    """

    def __init__(self, storage_path: Path) -> None:
        self._storage_path = storage_path
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._gate = LockedTestGate.restore(self._read_records())

    def _read_records(self) -> list[LockedTestAuditRecord]:
        if not self._storage_path.exists():
            return []
        records = []
        with self._storage_path.open(encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if line:
                    records.append(_audit_record_from_dict(json.loads(line)))
        return records

    def is_unlocked(self, experiment_id: str) -> bool:
        return self._gate.is_unlocked(experiment_id)

    def unlock(self, *, experiment_id: str, reason: str, actor: str) -> LockedTestAuditRecord:
        record = self._gate.unlock(experiment_id=experiment_id, reason=reason, actor=actor)
        with self._storage_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(_audit_record_to_dict(record), ensure_ascii=False) + "\n")
        return record

    def assert_unlocked(self, experiment_id: str) -> None:
        self._gate.assert_unlocked(experiment_id)

    def audit_trail(self) -> tuple[LockedTestAuditRecord, ...]:
        return self._gate.audit_trail()


__all__ = [
    "AccessStage",
    "FileBackedLockedTestGate",
    "LockedTestAuditRecord",
    "LockedTestGate",
    "LockedTestGateProtocol",
]
