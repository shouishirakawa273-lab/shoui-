"""Tamper Evidence: Deterministic Canonical Hash + Integrity Verification(D0107)。

"Immutable"は「Update Methodが存在しない」以上の意味を持つ(D0107 §18)。
本Moduleは、D0107の各Immutable Record(`PredictionRecord`/
`EvaluationContract`/`ExperimentSpec`等)が構築後に改変されていないことを
検証するための、唯一の決定論的Hash計算・検証Primitiveを提供する。

新しいHash Algorithmは作らない——既存`lib.reproducibility.
hash_json_safe()`(JSON `sort_keys=True`、SHA-256)をそのまま再利用する
(D0102.1以降、Repository全体で一貫して使われているCanonical Hash)。
本Moduleが追加するのは、Dataclass Instance(Enum/Decimal/datetime/
Nested Dataclassを含む)をJSON-Safeな入れ子Dict/Listへ変換する
`to_hashable()`のみである。

`record_hash`はHash対象から自身を除外する(D0107 §18「Hash must
exclude its own hash field」)。Tuple等のSequence Fieldは、呼び出し側
(各`build_*()`関数)が構築時にCanonical Order(通常`sorted()`)へ
正規化してから渡す責務を持つ——本Module自身はSequenceの並び替えを
行わない(Section論理的に同値な内容であれば順序を変えてもHashが変わら
ないことを保証するのは、各Recordの構築Layer側のCanonicalization責務、
D0107 §18 TEST K)。
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from lib.reproducibility import hash_json_safe


def to_hashable(value: object) -> object:
    """任意のValueをJSON-Safeな入れ子Primitive(dict/list/str/int/
    bool/None)へ再帰的に変換する。`StrEnum`等のEnumは`.value`へ、
    `datetime`/`date`は`isoformat()`へ、`Decimal`は`str()`へ、Nested
    Frozen DataclassはField名でソートしたdictへ変換する——いずれも
    決定論的(同じValueからは常に同じ結果)。

    独自のHash Algorithmはここでは作らない(最終的なHash計算は
    `compute_record_hash()`経由で既存`hash_json_safe()`に委ねる)。
    """
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, tuple | list):
        return [to_hashable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): to_hashable(v) for k, v in value.items()}
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_hashable(getattr(value, f.name)) for f in fields(value)}
    return value


def compute_record_hash(payload: dict[str, Any]) -> str:
    """`payload`(通常は対象Recordの`record_hash`を除く全Field)から
    決定論的SHA-256 Hashを計算する唯一のEntrypoint(D0107 §18)。
    `payload`自体に`record_hash`Keyが含まれていた場合は、計算対象から
    明示的に除外する(自己参照を防ぐ、D0107 §18「Hash must exclude its
    own hash field」)。"""
    sanitized = {k: to_hashable(v) for k, v in payload.items() if k != "record_hash"}
    return hash_json_safe(sanitized)


def verify_record_integrity(record: object, *, expected_hash_field: str = "record_hash") -> bool:
    """`record`(Frozen Dataclass、`record_hash`相当のField名は
    `expected_hash_field`で指定)の現在の内容から再計算したHashが、
    保持されている`record_hash`と一致するかを検証する(D0107 §19)。
    不一致の場合はFalseを返すのみで、自動修復(Silent Repair)は一切
    行わない。

    `record`をそのままJSON等でSerialize/Deserializeした結果に対しても
    同じ検証ができるよう、本関数はDataclass Instanceを要求する
    (呼び出し側がDeserialize後に対応するDataclassへ戻してから渡す、
    D0107 §19)。"""
    if not is_dataclass(record) or isinstance(record, type):
        raise TypeError(f"record は Frozen Dataclass Instance である必要があります: {record!r}")
    stored_hash = getattr(record, expected_hash_field)
    payload = {f.name: getattr(record, f.name) for f in fields(record) if f.name != expected_hash_field}
    recomputed = compute_record_hash(payload)
    return bool(recomputed == stored_hash)


__all__ = ["compute_record_hash", "to_hashable", "verify_record_integrity"]
