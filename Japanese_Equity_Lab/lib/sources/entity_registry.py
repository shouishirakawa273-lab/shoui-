"""Canonical Entity Registry: J-Quants Code/EDINET Code/法人番号/社名等を直接joinしない。

Multi-Source統合では、同じ発行体(issuer)が Source ごとに別々の識別子(J-Quants
Provider Code、EDINET Code、法人番号、社名・旧社名等)を持つ。これらを文字列の
一致だけで直接joinすると、コード体系の変更・社名変更・類似名の別会社等により
誤ったjoinを引き起こしうる。このモジュールは、それらの識別子をCanonical ID
(`issuer_id`)を介して間接的に対応付ける(D0040)。

**Identifier MappingにもPoint-in-Time原則を適用する**: 同じProviderの同じ識別子でも、
発行体側のCorporate Action(社名変更・コード変更・上場廃止後の再上場等)により、
時期によって対応するissuer_idが変わりうる。`valid_from`/`valid_until`で有効期間を
明示し、`resolve()`は`as_of`を指定して問い合わせる(値が不明な場合は`None`を返し、
架空の対応付けを行わない)。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum


class MappingConfidence(StrEnum):
    """この識別子対応付けがどの程度確からしいか(内容の正しさではなく対応付けの確からしさ)。"""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"


@dataclass(kw_only=True, frozen=True)
class EntityIdentifierMapping:
    """1つの発行体(issuer)についての、ある有効期間におけるIdentifier対応付け。

    `provider_identifiers`は「Provider名 -> そのProviderが使う生の識別子」の対応
    (例: ``{"jquants": "72030", "edinet": "E02166"}``)。同じissuer_idについて、
    有効期間が異なる複数の`EntityIdentifierMapping`を登録できる(社名変更・
    コード変更等を表現するため)。
    """

    issuer_id: str
    security_id: str | None = None
    provider_identifiers: Mapping[str, str] = field(default_factory=dict)
    aliases: tuple[str, ...] = field(default_factory=tuple)
    canonical_name: str
    valid_from: date | None = None
    valid_until: date | None = None
    mapping_provenance: str | None = None
    mapping_confidence: MappingConfidence = MappingConfidence.UNKNOWN

    def _is_valid_on(self, as_of: date) -> bool:
        if self.valid_from is not None and as_of < self.valid_from:
            return False
        if self.valid_until is not None and as_of >= self.valid_until:
            return False
        return True


class EntityRegistry:
    """`EntityIdentifierMapping`の集合から、as_of時点でのissuer_idを解決する。"""

    def __init__(self, mappings: Sequence[EntityIdentifierMapping] = ()) -> None:
        self._mappings = list(mappings)

    def register(self, mapping: EntityIdentifierMapping) -> None:
        self._mappings.append(mapping)

    def resolve(self, *, provider_name: str, provider_identifier: str, as_of: date) -> EntityIdentifierMapping | None:
        """as_of時点で有効な、provider_identifierに対応するMappingを返す。

        該当が無い場合は`None`(架空の対応付けをしない)。複数マッチした場合
        (=データ不整合、有効期間が重複している)は`ValueError`とする
        (黙ってどちらかを選ばない)。
        """
        if as_of is None:
            raise ValueError("as_of の指定が必須です")
        matches = [
            m
            for m in self._mappings
            if m.provider_identifiers.get(provider_name) == provider_identifier and m._is_valid_on(as_of)
        ]
        if len(matches) > 1:
            raise ValueError(
                f"provider_name={provider_name} provider_identifier={provider_identifier} as_of={as_of} で"
                f"複数のEntityIdentifierMappingが一致しました(有効期間の重複、データ不整合の可能性): {matches}"
            )
        return matches[0] if matches else None

    def all(self) -> tuple[EntityIdentifierMapping, ...]:
        return tuple(self._mappings)
