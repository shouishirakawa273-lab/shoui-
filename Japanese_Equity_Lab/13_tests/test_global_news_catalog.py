"""`lib.news.catalog`のGlobal News候補(Phase4E-3)向けTest。既存Japan News
Catalog Test(`test_news_catalog.py`)と同じPattern——最初からCatalog Test
を追加する(Positioning/Macro/Global MarketでCatalog TestがGap後追いだった
教訓を活かす、Phase4E-2からの継続方針)。
"""

from __future__ import annotations

import pytest
from lib.news.catalog import (
    build_fsa_press_release_dataset_descriptor,
    build_gdelt_doc_dataset_descriptor,
    build_jpx_news_releases_dataset_descriptor,
    build_meti_news_release_dataset_descriptor,
    build_prtimes_dataset_descriptor,
    build_sec_press_release_dataset_descriptor,
)
from lib.sources.catalog import DataCapability, ImplementationStatus, SourceAuthorityClass, SourceCatalog

_GLOBAL_NEWS_BUILDERS = (
    build_gdelt_doc_dataset_descriptor,
    build_sec_press_release_dataset_descriptor,
)

_ALL_NEWS_BUILDERS = (
    build_prtimes_dataset_descriptor,
    build_jpx_news_releases_dataset_descriptor,
    build_fsa_press_release_dataset_descriptor,
    build_meti_news_release_dataset_descriptor,
    build_gdelt_doc_dataset_descriptor,
    build_sec_press_release_dataset_descriptor,
)


def test_all_news_datasets_including_global_register_without_duplicate_id_conflict() -> None:
    catalog = SourceCatalog([builder() for builder in _ALL_NEWS_BUILDERS])
    found = catalog.find(capability=DataCapability.NEWS)
    assert len(found) == 6


def test_global_news_candidates_are_not_implemented_and_not_pit_available() -> None:
    """未検証SourceをLIVE_VALIDATED/CONNECTEDと記録しない(Phase4E-3要件§38、
    Phase4E-2要件§8を踏襲)。このRoundはAdapterを1件も実装していない。"""
    for builder in _GLOBAL_NEWS_BUILDERS:
        descriptor = builder()
        assert descriptor.implementation_status == ImplementationStatus.NOT_IMPLEMENTED, descriptor.dataset_id
        assert descriptor.pit_available is False, descriptor.dataset_id


def test_global_news_candidates_disclose_design_complete_awaiting_spec_verification() -> None:
    """検索Snippetだけを根拠にAdapterを実装しなかったことを、Known
    Limitationsが正直に開示していることを直接確認する(Phase4E-3要件§33)。"""
    for builder in _GLOBAL_NEWS_BUILDERS:
        descriptor = builder()
        assert "DESIGN_COMPLETE_AWAITING_SPEC_VERIFICATION" in descriptor.known_limitations, descriptor.dataset_id


def test_dataset_ids_are_all_distinct_across_japan_and_global_news() -> None:
    ids = [builder().dataset_id for builder in _ALL_NEWS_BUILDERS]
    assert len(ids) == len(set(ids))


def test_duplicate_registration_of_gdelt_raises() -> None:
    catalog = SourceCatalog([build_gdelt_doc_dataset_descriptor()])
    with pytest.raises(ValueError, match="重複"):
        catalog.register(build_gdelt_doc_dataset_descriptor())


def test_gdelt_authority_class_is_verified_secondary_not_primary_official() -> None:
    """GDELTは複数News SourceをMonitoringするSecondary Aggregatorであり、
    記事のOriginating Source自体ではない(Phase4E-3要件§33)。"""
    descriptor = build_gdelt_doc_dataset_descriptor()
    assert descriptor.authority_class == SourceAuthorityClass.VERIFIED_SECONDARY


def test_sec_authority_class_is_primary_official() -> None:
    descriptor = build_sec_press_release_dataset_descriptor()
    assert descriptor.authority_class == SourceAuthorityClass.PRIMARY_OFFICIAL


def test_sec_known_limitations_mention_timezone_abbreviation_ambiguity() -> None:
    """GNEWS-004(Ambiguous Timezone Abbreviation Rejected)の原則がCatalog
    Known Limitationsにも一貫して記録されていることを確認する(SECの
    "EST"年間固定Label疑義、D0056/Phase4E-3要件§14)。"""
    descriptor = build_sec_press_release_dataset_descriptor()
    assert "EST" in descriptor.known_limitations
    assert "IANA" in descriptor.known_limitations


def test_gdelt_known_limitations_disclose_metadata_only_not_full_text() -> None:
    """GDELTがEvent-level Metadataのみを配信し、News全文を保存できる
    Sourceではないことを、Catalog自身が正直に開示していることを確認する
    (Copyright/Compliance原則、Phase4E-3要件§24/§26)。"""
    descriptor = build_gdelt_doc_dataset_descriptor()
    assert "Event-level Metadata" in descriptor.known_limitations
    assert "REFERENCE_ONLY" in descriptor.known_limitations


def test_global_news_datasets_not_found_under_unrelated_capability() -> None:
    catalog = SourceCatalog([build_gdelt_doc_dataset_descriptor(), build_sec_press_release_dataset_descriptor()])
    assert catalog.find(capability=DataCapability.MACRO) == ()
