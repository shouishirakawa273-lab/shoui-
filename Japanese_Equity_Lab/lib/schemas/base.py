"""全schema共通のメタデータ(schema_version / created_at / updated_at / provenance)。

将来schemaのフィールドが変わっても追跡できるよう、全てのレコード型はこれを継承する。
値オブジェクトとして扱うため frozen=True とし、変更は常に dataclasses.replace() で
新しいインスタンスを作ることで表現する(raw dataをimmutableに保つ方針と一致させる)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

SCHEMA_VERSION = "1.0"


@dataclass(kw_only=True, frozen=True)
class RecordMeta:
    schema_version: str = SCHEMA_VERSION
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    source: str = "manual"
    provenance_id: str | None = None
