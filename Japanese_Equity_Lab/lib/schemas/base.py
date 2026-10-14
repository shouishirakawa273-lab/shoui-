"""全schema共通のメタデータ(schema_version / created_at / updated_at / provenance)。

将来schemaのフィールドが変わっても追跡できるよう、全てのレコード型はこれを継承する。
値オブジェクトとして扱うため frozen=True とし、変更は常に dataclasses.replace() で
新しいインスタンスを作ることで表現する(raw dataをimmutableに保つ方針と一致させる)。

## `updated_at` の意味(version semantics)

このリポジトリには「1行を書き換えるDBレコード」は存在しない。全schemaはfrozenな
値オブジェクトであり、変更は必ず dataclasses.replace() で新しいPythonオブジェクトを
作ることで表される。したがって:

- `created_at`: このオブジェクト(スナップショット)が最初に作られた時刻。
- `updated_at`: このオブジェクト(スナップショット)が最後に導出・確定した時刻。
  `replace()` で派生させた新しいインスタンスは、通常 `updated_at` を呼び出し時刻に
  更新する(例: `Hypothesis.lock()` / `with_status()`)。**既存の永続化済みファイル
  (Markdown/JSON)を書き換えて`updated_at`だけ差し替える、という使い方はしない。**
  ライフサイクル遷移(Hypothesisのstatus等)は同じ `hypothesis_id` のまま新しい
  スナップショットを保存する(ファイルを上書きするか、追記専用ストアに記録するかは
  各schemaの利用者側で決める)。条件(terms)そのものが変わる場合は
  `Hypothesis.revise()` のように新しいIDを発行し、元のレコードは一切変更しない。

## Record versioning(record_id / record_version / supersedes_record_id / content_hash)は未導入

汎用的なバージョン管理フィールドの導入を検討したが、Phase1.1では見送った
(DECISIONS.md D0010参照)。`Hypothesis` は既に `parent_hypothesis_id` +
`locked_terms_hash` という専用の系譜追跡を持っており、他のschema(Idea/Strategy/
Knowledge等)は現時点で改訂(revise)の実運用例が無いため、汎用スキームを先に
設計すると過剰設計になるリスクがある。必要になった時点で `Hypothesis` のパターンを
一般化する。
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
