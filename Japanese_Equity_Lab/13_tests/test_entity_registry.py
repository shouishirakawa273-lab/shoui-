"""Phase3D(D0040): Canonical Entity Registry(PIT-aware Identifier Mapping)のテスト。"""

from __future__ import annotations

from datetime import date

import pytest
from lib.sources.entity_registry import EntityIdentifierMapping, EntityRegistry, MappingConfidence


def test_resolve_returns_mapping_valid_at_as_of() -> None:
    """社名/コード変更で有効期間が分かれている場合、as_ofに応じて正しいMappingを返す。"""
    registry = EntityRegistry(
        [
            EntityIdentifierMapping(
                issuer_id="ISSUER_0001",
                provider_identifiers={"jquants": "9999"},
                canonical_name="旧社名株式会社",
                valid_from=date(2000, 1, 1),
                valid_until=date(2020, 1, 1),
                mapping_confidence=MappingConfidence.HIGH,
            ),
            EntityIdentifierMapping(
                issuer_id="ISSUER_0001",
                provider_identifiers={"jquants": "1234"},
                canonical_name="新社名株式会社",
                valid_from=date(2020, 1, 1),
                valid_until=None,
                mapping_confidence=MappingConfidence.HIGH,
            ),
        ]
    )
    before = registry.resolve(provider_name="jquants", provider_identifier="9999", as_of=date(2010, 1, 1))
    after = registry.resolve(provider_name="jquants", provider_identifier="1234", as_of=date(2024, 1, 1))
    assert before is not None
    assert before.canonical_name == "旧社名株式会社"
    assert after is not None
    assert after.canonical_name == "新社名株式会社"


def test_resolve_returns_none_outside_validity_range_not_guessed() -> None:
    registry = EntityRegistry(
        [
            EntityIdentifierMapping(
                issuer_id="ISSUER_0001",
                provider_identifiers={"jquants": "9999"},
                canonical_name="旧社名株式会社",
                valid_from=date(2000, 1, 1),
                valid_until=date(2020, 1, 1),
            )
        ]
    )
    # 旧コードでの解決を、有効期間外(切替後)のas_ofで問い合わせても解決しない(架空の対応付けをしない)。
    result = registry.resolve(provider_name="jquants", provider_identifier="9999", as_of=date(2024, 1, 1))
    assert result is None


def test_resolve_returns_none_for_unknown_identifier() -> None:
    registry = EntityRegistry([])
    assert registry.resolve(provider_name="jquants", provider_identifier="0000", as_of=date(2024, 1, 1)) is None


def test_resolve_raises_on_overlapping_validity_ranges() -> None:
    """有効期間が重複するデータ不整合は、黙ってどちらかを選ばずエラーにする。"""
    registry = EntityRegistry(
        [
            EntityIdentifierMapping(
                issuer_id="ISSUER_A",
                provider_identifiers={"jquants": "9999"},
                canonical_name="A社",
                valid_from=date(2000, 1, 1),
                valid_until=date(2025, 1, 1),
            ),
            EntityIdentifierMapping(
                issuer_id="ISSUER_B",
                provider_identifiers={"jquants": "9999"},
                canonical_name="B社(データ不整合を模擬)",
                valid_from=date(2020, 1, 1),
                valid_until=None,
            ),
        ]
    )
    with pytest.raises(ValueError, match="複数"):
        registry.resolve(provider_name="jquants", provider_identifier="9999", as_of=date(2022, 1, 1))


def test_provider_identifiers_keeps_multiple_providers_distinct() -> None:
    mapping = EntityIdentifierMapping(
        issuer_id="ISSUER_0001",
        provider_identifiers={"jquants": "72030", "edinet": "E02166"},
        canonical_name="トヨタ自動車",
    )
    registry = EntityRegistry([mapping])
    via_jquants = registry.resolve(provider_name="jquants", provider_identifier="72030", as_of=date(2024, 1, 1))
    via_edinet = registry.resolve(provider_name="edinet", provider_identifier="E02166", as_of=date(2024, 1, 1))
    assert via_jquants is not None and via_jquants.issuer_id == "ISSUER_0001"
    assert via_edinet is not None and via_edinet.issuer_id == "ISSUER_0001"
    # J-QuantsのProvider識別子でEDINET識別子を検索しても一致しない(直接joinしない)。
    assert registry.resolve(provider_name="edinet", provider_identifier="72030", as_of=date(2024, 1, 1)) is None
