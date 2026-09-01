"""`lib.macro.catalog`のTest(Phase4D)。Phase4C(Positioning)のskeptic-reviewer
Findingで、Catalog Descriptor群にTest Coverageが無かったGapが指摘された
教訓を活かし、このRoundでは最初からCatalog Testを追加する。
"""

from __future__ import annotations

import pytest
from lib.macro.catalog import (
    build_boj_policy_rate_dataset_descriptor,
    build_esri_gdp_qe_dataset_descriptor,
    build_estat_cpi_dataset_descriptor,
    build_estat_unemployment_rate_dataset_descriptor,
    build_mhlw_monthly_labour_survey_dataset_descriptor,
)
from lib.sources.catalog import DataCapability, ImplementationStatus, SourceCatalog

_ALL_BUILDERS = (
    build_estat_cpi_dataset_descriptor,
    build_boj_policy_rate_dataset_descriptor,
    build_esri_gdp_qe_dataset_descriptor,
    build_estat_unemployment_rate_dataset_descriptor,
    build_mhlw_monthly_labour_survey_dataset_descriptor,
)


def test_all_macro_datasets_register_without_duplicate_id_conflict() -> None:
    catalog = SourceCatalog([builder() for builder in _ALL_BUILDERS])
    found = catalog.find(capability=DataCapability.MACRO)
    assert len(found) == 5


def test_all_macro_candidates_are_not_implemented_and_not_pit_available() -> None:
    """未検証SourceをLIVE_VALIDATED/CONNECTEDと記録しない(Phase4D要件§38)。
    このRoundはAdapterを1件も実装していないため、5件全てNOT_IMPLEMENTED。"""
    for builder in _ALL_BUILDERS:
        descriptor = builder()
        assert descriptor.implementation_status == ImplementationStatus.NOT_IMPLEMENTED, descriptor.dataset_id
        assert descriptor.pit_available is False, descriptor.dataset_id


def test_all_macro_candidates_disclose_design_complete_awaiting_spec_verification() -> None:
    """検索Snippetだけを根拠にAdapterを実装しなかったことを、Known
    Limitationsが正直に開示していることを直接確認する(Phase4D要件§33)。"""
    for builder in _ALL_BUILDERS:
        descriptor = builder()
        assert "DESIGN_COMPLETE_AWAITING_SPEC_VERIFICATION" in descriptor.known_limitations, descriptor.dataset_id


def test_macro_datasets_not_found_under_unrelated_capability() -> None:
    catalog = SourceCatalog([build_estat_cpi_dataset_descriptor()])
    assert catalog.find(capability=DataCapability.NEWS) == ()


def test_dataset_ids_are_all_distinct() -> None:
    ids = [builder().dataset_id for builder in _ALL_BUILDERS]
    assert len(ids) == len(set(ids))


def test_duplicate_registration_raises() -> None:
    catalog = SourceCatalog([build_estat_cpi_dataset_descriptor()])
    with pytest.raises(ValueError, match="重複"):
        catalog.register(build_estat_cpi_dataset_descriptor())


def test_all_source_authority_classes_are_primary_official() -> None:
    """5候補はいずれも政府/中央銀行が運営する統計であり、PRIMARY_OFFICIALで
    あることを確認する(Company Primary等と混同しない)。"""
    from lib.sources.catalog import SourceAuthorityClass

    for builder in _ALL_BUILDERS:
        descriptor = builder()
        assert descriptor.authority_class == SourceAuthorityClass.PRIMARY_OFFICIAL, descriptor.dataset_id
