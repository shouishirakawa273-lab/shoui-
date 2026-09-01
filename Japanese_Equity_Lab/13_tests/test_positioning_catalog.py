"""`lib.positioning.catalog`のTest(Phase4C)。pit-auditor/skeptic-reviewer
Reviewで指摘された、Catalog Descriptor群がTest Coverage無しでRepositoryに
存在していたGapへの修正(`lib.fundamentals.catalog`/`lib.disclosures.catalog`
と同じ`SourceCatalog`統合Testパターンを踏襲する)。
"""

from __future__ import annotations

import pytest
from lib.positioning.catalog import (
    build_jquants_short_ratio_dataset_descriptor,
    build_jquants_short_sale_report_dataset_descriptor,
    build_jquants_trades_spec_dataset_descriptor,
    build_jquants_weekly_margin_interest_dataset_descriptor,
    build_price_derived_liquidity_dataset_descriptor,
)
from lib.sources.catalog import DataCapability, ImplementationStatus, SourceCatalog

_ALL_BUILDERS = (
    build_price_derived_liquidity_dataset_descriptor,
    build_jquants_weekly_margin_interest_dataset_descriptor,
    build_jquants_short_ratio_dataset_descriptor,
    build_jquants_short_sale_report_dataset_descriptor,
    build_jquants_trades_spec_dataset_descriptor,
)


def test_all_positioning_datasets_register_without_duplicate_id_conflict() -> None:
    catalog = SourceCatalog([builder() for builder in _ALL_BUILDERS])
    found = catalog.find(capability=DataCapability.POSITIONING)
    assert len(found) == 5


def test_price_derived_liquidity_is_connected_and_pit_available() -> None:
    catalog = SourceCatalog([build_price_derived_liquidity_dataset_descriptor()])
    found = catalog.find(capability=DataCapability.POSITIONING)
    assert [d.dataset_id for d in found] == ["price_derived_liquidity"]
    assert found[0].implementation_status == ImplementationStatus.CONNECTED
    assert found[0].pit_available is True


def test_unimplemented_jquants_candidates_are_not_implemented_and_not_pit_available() -> None:
    """未検証Sourceを`LIVE_VALIDATED`/`CONNECTED`と記録しない(Phase4C要件§37)。"""
    unimplemented_builders = (
        build_jquants_weekly_margin_interest_dataset_descriptor,
        build_jquants_short_ratio_dataset_descriptor,
        build_jquants_short_sale_report_dataset_descriptor,
        build_jquants_trades_spec_dataset_descriptor,
    )
    for builder in unimplemented_builders:
        descriptor = builder()
        assert descriptor.implementation_status == ImplementationStatus.NOT_IMPLEMENTED, descriptor.dataset_id
        assert descriptor.pit_available is False, descriptor.dataset_id


def test_unimplemented_candidates_known_limitations_disclose_unverified_status() -> None:
    """SEARCH-SNIPPET-DERIVED(UNVERIFIED)であることをKnown Limitationsが
    正直に開示していることを直接確認する(推測をConfirmedのように書かない)。"""
    unimplemented_builders = (
        build_jquants_weekly_margin_interest_dataset_descriptor,
        build_jquants_short_ratio_dataset_descriptor,
        build_jquants_short_sale_report_dataset_descriptor,
        build_jquants_trades_spec_dataset_descriptor,
    )
    for builder in unimplemented_builders:
        descriptor = builder()
        assert "PENDING" in descriptor.known_limitations, descriptor.dataset_id


def test_positioning_datasets_not_found_under_unrelated_capability() -> None:
    catalog = SourceCatalog([build_price_derived_liquidity_dataset_descriptor()])
    assert catalog.find(capability=DataCapability.NEWS) == ()


def test_dataset_ids_are_all_distinct() -> None:
    ids = [builder().dataset_id for builder in _ALL_BUILDERS]
    assert len(ids) == len(set(ids))


def test_duplicate_registration_raises() -> None:
    catalog = SourceCatalog([build_price_derived_liquidity_dataset_descriptor()])
    with pytest.raises(ValueError, match="重複"):
        catalog.register(build_price_derived_liquidity_dataset_descriptor())
