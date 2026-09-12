"""`lib.global_market.catalog`のTest(Phase4E-1)。Positioning Phase4C・
Macro Phase4Dのskeptic-reviewer Findingで、Catalog Descriptor群に
Test Coverageが無かった/後追いだったGapが指摘された教訓を活かし、
このRoundでは最初からCatalog Testを追加する。
"""

from __future__ import annotations

import pytest
from lib.global_market.catalog import (
    build_fred_dexjpus_dataset_descriptor,
    build_fred_dexuseu_dataset_descriptor,
    build_fred_dgs10_dataset_descriptor,
    build_fred_sp500_dataset_descriptor,
    build_fred_vixcls_dataset_descriptor,
)
from lib.sources.catalog import DataCapability, ImplementationStatus, SourceAuthorityClass, SourceCatalog

_ALL_BUILDERS = (
    build_fred_sp500_dataset_descriptor,
    build_fred_dexjpus_dataset_descriptor,
    build_fred_dexuseu_dataset_descriptor,
    build_fred_dgs10_dataset_descriptor,
    build_fred_vixcls_dataset_descriptor,
)


def test_all_global_market_datasets_register_without_duplicate_id_conflict() -> None:
    catalog = SourceCatalog([builder() for builder in _ALL_BUILDERS])
    found = catalog.find(capability=DataCapability.GLOBAL_MARKET)
    assert len(found) == 5


def test_all_global_market_candidates_are_not_implemented_and_not_pit_available() -> None:
    """未検証SourceをLIVE_VALIDATED/CONNECTEDと記録しない(Phase4E-1要件§8)。
    このRoundはAdapterを1件も実装していないため、5件全てNOT_IMPLEMENTED。"""
    for builder in _ALL_BUILDERS:
        descriptor = builder()
        assert descriptor.implementation_status == ImplementationStatus.NOT_IMPLEMENTED, descriptor.dataset_id
        assert descriptor.pit_available is False, descriptor.dataset_id


def test_all_global_market_candidates_disclose_design_complete_awaiting_spec_verification() -> None:
    """検索Snippetだけを根拠にAdapterを実装しなかったことを、Known
    Limitationsが正直に開示していることを直接確認する(Phase4E-1要件§8)。"""
    for builder in _ALL_BUILDERS:
        descriptor = builder()
        assert "DESIGN_COMPLETE_AWAITING_SPEC_VERIFICATION" in descriptor.known_limitations, descriptor.dataset_id


def test_global_market_datasets_not_found_under_unrelated_capability() -> None:
    catalog = SourceCatalog([build_fred_sp500_dataset_descriptor()])
    assert catalog.find(capability=DataCapability.NEWS) == ()


def test_dataset_ids_are_all_distinct() -> None:
    ids = [builder().dataset_id for builder in _ALL_BUILDERS]
    assert len(ids) == len(set(ids))


def test_duplicate_registration_raises() -> None:
    catalog = SourceCatalog([build_fred_sp500_dataset_descriptor()])
    with pytest.raises(ValueError, match="重複"):
        catalog.register(build_fred_sp500_dataset_descriptor())


def test_all_source_authority_classes_are_primary_official() -> None:
    """5候補はいずれもFRED(セントルイス連銀)経由だが、原典はいずれも公的
    機関(S&P DJI/Nasdaq/連邦準備制度理事会/米財務省/CBOE)であり、
    PRIMARY_OFFICIALであることを確認する。"""
    for builder in _ALL_BUILDERS:
        descriptor = builder()
        assert descriptor.authority_class == SourceAuthorityClass.PRIMARY_OFFICIAL, descriptor.dataset_id


def test_fx_candidates_are_distinguished_by_currency_pair_not_merged() -> None:
    """USD/JPYとEUR/USDは別Dataset(GLOBAL-007 Index Identity原則のFX版)。"""
    jpy_descriptor = build_fred_dexjpus_dataset_descriptor()
    eur_descriptor = build_fred_dexuseu_dataset_descriptor()
    assert jpy_descriptor.dataset_id != eur_descriptor.dataset_id
    assert jpy_descriptor.applicable_countries != eur_descriptor.applicable_countries


def test_vix_descriptor_discloses_originating_source_versus_delivery_provider_separation() -> None:
    """VIXはCBOEが原典・FREDが配信層(SOURCE-004原則)であることが
    Known Limitationsに明記されていることを確認する。"""
    descriptor = build_fred_vixcls_dataset_descriptor()
    assert "CBOE" in descriptor.known_limitations
    assert "配信層" in descriptor.known_limitations
