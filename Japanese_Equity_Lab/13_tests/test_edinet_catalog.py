"""Phase4B-2: EDINETのSource Catalog登録(`build_edinet_dataset_descriptor`)のテスト。"""

from __future__ import annotations

from lib.disclosures.catalog import build_disclosure_common_core_dataset_descriptor, build_edinet_dataset_descriptor
from lib.sources.catalog import DataCapability, ImplementationStatus, SourceAuthorityClass, SourceCatalog


def test_edinet_registered_under_disclosure_capability_as_not_implemented() -> None:
    catalog = SourceCatalog([build_edinet_dataset_descriptor()])
    found = catalog.find(capability=DataCapability.DISCLOSURE)
    assert [d.dataset_id for d in found] == ["edinet_disclosures"]
    assert found[0].implementation_status == ImplementationStatus.NOT_IMPLEMENTED
    assert found[0].pit_available is False


def test_edinet_authority_class_is_primary_official_but_not_used_as_truth_score() -> None:
    """PRIMARY_OFFICIAL(FSA公式Source)であっても、それ自体が内容の正しさを保証しない
    ことは`SourceAuthorityClass`自体のDocstringが既に明記している。ここでは単に
    Catalog上の分類が正しく設定されていることのみ確認する。"""
    descriptor = build_edinet_dataset_descriptor()
    assert descriptor.authority_class == SourceAuthorityClass.PRIMARY_OFFICIAL


def test_edinet_and_disclosure_common_core_coexist_in_catalog() -> None:
    """Disclosure Common Core(Architecture自体)とEDINET(実Source)は別Datasetとして
    共存する(既存Descriptorを書き換えるのではなく追加する、という設計の確認)。"""
    catalog = SourceCatalog([build_disclosure_common_core_dataset_descriptor(), build_edinet_dataset_descriptor()])
    found = catalog.find(capability=DataCapability.DISCLOSURE)
    assert {d.dataset_id for d in found} == {"disclosure_common_core", "edinet_disclosures"}


def test_edinet_known_limitations_references_onboarding_report() -> None:
    descriptor = build_edinet_dataset_descriptor()
    assert "EDINET_SOURCE_ONBOARDING" in descriptor.known_limitations
