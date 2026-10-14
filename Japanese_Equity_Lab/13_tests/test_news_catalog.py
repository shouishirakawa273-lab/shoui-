"""`lib.news.catalog`のTest(Phase4E-2)。Positioning/Macro/Global Marketの
skeptic-reviewer Findingで、Catalog Descriptor群にTest Coverageが無かった/
後追いだったGapが指摘された教訓を活かし、このRoundでは最初からCatalog
Testを追加する。
"""

from __future__ import annotations

import pytest
from lib.news.catalog import (
    build_fsa_press_release_dataset_descriptor,
    build_jpx_news_releases_dataset_descriptor,
    build_meti_news_release_dataset_descriptor,
    build_prtimes_dataset_descriptor,
)
from lib.sources.catalog import DataCapability, ImplementationStatus, SourceAuthorityClass, SourceCatalog

_ALL_BUILDERS = (
    build_prtimes_dataset_descriptor,
    build_jpx_news_releases_dataset_descriptor,
    build_fsa_press_release_dataset_descriptor,
    build_meti_news_release_dataset_descriptor,
)


def test_all_news_datasets_register_without_duplicate_id_conflict() -> None:
    catalog = SourceCatalog([builder() for builder in _ALL_BUILDERS])
    found = catalog.find(capability=DataCapability.NEWS)
    assert len(found) == 4


def test_all_news_candidates_are_not_implemented_and_not_pit_available() -> None:
    """未検証SourceをLIVE_VALIDATED/CONNECTEDと記録しない(Phase4E-2要件§8)。
    このRoundはAdapterを1件も実装していないため、4件全てNOT_IMPLEMENTED。"""
    for builder in _ALL_BUILDERS:
        descriptor = builder()
        assert descriptor.implementation_status == ImplementationStatus.NOT_IMPLEMENTED, descriptor.dataset_id
        assert descriptor.pit_available is False, descriptor.dataset_id


def test_all_news_candidates_disclose_design_complete_awaiting_spec_verification() -> None:
    """検索Snippetだけを根拠にAdapterを実装しなかったことを、Known
    Limitationsが正直に開示していることを直接確認する(Phase4E-2要件§8)。"""
    for builder in _ALL_BUILDERS:
        descriptor = builder()
        assert "DESIGN_COMPLETE_AWAITING_SPEC_VERIFICATION" in descriptor.known_limitations, descriptor.dataset_id


def test_news_datasets_not_found_under_unrelated_capability() -> None:
    catalog = SourceCatalog([build_prtimes_dataset_descriptor()])
    assert catalog.find(capability=DataCapability.MACRO) == ()


def test_dataset_ids_are_all_distinct() -> None:
    ids = [builder().dataset_id for builder in _ALL_BUILDERS]
    assert len(ids) == len(set(ids))


def test_duplicate_registration_raises() -> None:
    catalog = SourceCatalog([build_prtimes_dataset_descriptor()])
    with pytest.raises(ValueError, match="重複"):
        catalog.register(build_prtimes_dataset_descriptor())


def test_prtimes_authority_class_is_company_primary_not_primary_official() -> None:
    """PR TIMESはCompany発行Press Releaseの配信経路であり、Originating Source
    はCompany自身である(D0042 Originating/Delivery分離、TDnet=PRIMARY_
    OFFICIALとは異なりCOMPANY_PRIMARYとすべき)。"""
    descriptor = build_prtimes_dataset_descriptor()
    assert descriptor.authority_class == SourceAuthorityClass.COMPANY_PRIMARY


def test_official_regulator_and_exchange_candidates_are_primary_official() -> None:
    for builder in (
        build_jpx_news_releases_dataset_descriptor,
        build_fsa_press_release_dataset_descriptor,
        build_meti_news_release_dataset_descriptor,
    ):
        descriptor = builder()
        assert descriptor.authority_class == SourceAuthorityClass.PRIMARY_OFFICIAL, descriptor.dataset_id
