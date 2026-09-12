"""`lib.consensus.catalog`のTest(Phase4E-4)。既存Capability群のskeptic-
reviewer Findingで、Catalog Descriptor群にTest Coverageが無かった/後追い
だったGapが指摘された教訓を活かし、このRoundでは最初からCatalog Testを
追加する。
"""

from __future__ import annotations

import pytest
from lib.consensus.catalog import (
    build_ifis_japan_consensus_dataset_descriptor,
    build_quick_consensus_japan_dataset_descriptor,
)
from lib.sources.catalog import DataCapability, ImplementationStatus, SourceCatalog

_ALL_BUILDERS = (
    build_quick_consensus_japan_dataset_descriptor,
    build_ifis_japan_consensus_dataset_descriptor,
)


def test_all_consensus_datasets_register_without_duplicate_id_conflict() -> None:
    catalog = SourceCatalog([builder() for builder in _ALL_BUILDERS])
    found = catalog.find(capability=DataCapability.EXPECTATIONS)
    assert len(found) == 2


def test_all_consensus_candidates_are_not_implemented_and_not_pit_available() -> None:
    """未検証SourceをLIVE_VALIDATED/CONNECTEDと記録しない(Phase4E-4要件
    §50)。このRoundはAdapterを1件も実装していないため、2件全て
    NOT_IMPLEMENTED。"""
    for builder in _ALL_BUILDERS:
        descriptor = builder()
        assert descriptor.implementation_status == ImplementationStatus.NOT_IMPLEMENTED, descriptor.dataset_id
        assert descriptor.pit_available is False, descriptor.dataset_id


def test_all_consensus_candidates_disclose_design_complete_awaiting_spec_verification() -> None:
    """検索Snippetだけを根拠にAdapterを実装しなかったことを、Known
    Limitationsが正直に開示していることを直接確認する(Phase4E-4要件
    §9)。"""
    for builder in _ALL_BUILDERS:
        descriptor = builder()
        assert "DESIGN_COMPLETE_AWAITING_SPEC_VERIFICATION" in descriptor.known_limitations, descriptor.dataset_id


def test_consensus_datasets_not_found_under_unrelated_capability() -> None:
    catalog = SourceCatalog([build_quick_consensus_japan_dataset_descriptor()])
    assert catalog.find(capability=DataCapability.MACRO) == ()


def test_dataset_ids_are_all_distinct() -> None:
    ids = [builder().dataset_id for builder in _ALL_BUILDERS]
    assert len(ids) == len(set(ids))


def test_duplicate_registration_raises() -> None:
    catalog = SourceCatalog([build_quick_consensus_japan_dataset_descriptor()])
    with pytest.raises(ValueError, match="重複"):
        catalog.register(build_quick_consensus_japan_dataset_descriptor())


def test_no_registered_candidate_is_flagged_enterprise_only() -> None:
    """ENTERPRISE専用と判断したSource(FactSet/LSEG/Bloomberg/S&P Capital
    IQ/Visible Alpha)は、高品質・詳細なPIT設計であっても個人ローカル
    実行という本Labの前提にそぐわないためCatalogへ登録しない(Phase4E-4
    要件§10、Cost Reality、skeptic-reviewer Finding: FactSetのみ
    「Benchmark参照目的」で例外的に登録していたが、他のENTERPRISE専用
    候補への除外基準と矛盾していたため統一した)。登録された候補は
    いずれも`cost_or_plan_dependency`にENTERPRISEという確定的な記述を
    持たないことを直接確認する。"""
    for builder in _ALL_BUILDERS:
        descriptor = builder()
        assert "ENTERPRISE" not in descriptor.cost_or_plan_dependency, descriptor.dataset_id


def test_quick_consensus_is_the_top_ranked_japan_focused_candidate() -> None:
    descriptor = build_quick_consensus_japan_dataset_descriptor()
    assert descriptor.applicable_countries == ("JP",)
    assert "推奨順位1位" in descriptor.known_limitations


def test_ifis_known_limitations_disclose_weaker_pit_evidence_than_other_candidates() -> None:
    """このLabの最重要関心事(Historical Vintage支持)についてIFISが他候補
    より根拠が弱いことを、Catalog自身が正直に開示していることを確認する。"""
    descriptor = build_ifis_japan_consensus_dataset_descriptor()
    assert "見つからず" in descriptor.known_limitations
