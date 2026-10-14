"""Phase4B-3(D0047/D0048): TDnetのSource Catalog登録(`build_tdnet_dataset_descriptor`)のテスト。

D0047時点ではAdapter/Normalizerを一切実装していなかったが、D0048で
`EXTERNAL_OFFICIAL_SPEC_VERIFICATION`(ユーザーが別のWeb-access環境から
確認したと申告した内容)を根拠に`lib.disclosures.providers.tdnet.
TdnetAdapter`・`lib.disclosures.providers.tdnet_normalize`を実装した。
ただしこれはClaude自身がこのSession内で一次資料をFetchして確認したもの
ではなく、真のLocal Real Data Validationでもないため、`implementation_
status`は引き続き`NOT_IMPLEMENTED`・`pit_available=False`のまま維持する
(EDINETが辿った「まずコードを書き、後日ローカル環境の実呼び出しで
`CONNECTED`へ昇格させる」という手順の前半段階に相当)。
"""

from __future__ import annotations

from pathlib import Path

from lib.disclosures.catalog import (
    build_disclosure_common_core_dataset_descriptor,
    build_edinet_dataset_descriptor,
    build_tdnet_dataset_descriptor,
)
from lib.sources.catalog import DataCapability, ImplementationStatus, SourceAuthorityClass, SourceCatalog


def test_tdnet_registered_under_disclosure_capability_as_not_implemented() -> None:
    catalog = SourceCatalog([build_tdnet_dataset_descriptor()])
    found = catalog.find(capability=DataCapability.DISCLOSURE)
    assert [d.dataset_id for d in found] == ["tdnet_disclosures"]
    assert found[0].implementation_status == ImplementationStatus.NOT_IMPLEMENTED
    assert found[0].pit_available is False


def test_tdnet_authority_class_is_primary_official_but_not_used_as_truth_score() -> None:
    """TDnetはJPX運営の公式Venueであり出所としてはPRIMARY_OFFICIALが妥当だが、
    それ自体が内容の正しさ・実装済み度を保証しない(SourceAuthorityClass自体の
    Docstring参照)。Catalog上のImplementation Statusとは独立している。"""
    descriptor = build_tdnet_dataset_descriptor()
    assert descriptor.authority_class == SourceAuthorityClass.PRIMARY_OFFICIAL
    assert descriptor.implementation_status == ImplementationStatus.NOT_IMPLEMENTED


def test_tdnet_and_edinet_and_disclosure_common_core_coexist_in_catalog() -> None:
    """3つのDatasetは別々のDataset_idとして共存する(既存Descriptorを書き換える
    のではなく追加する、という設計の確認)。"""
    catalog = SourceCatalog(
        [
            build_disclosure_common_core_dataset_descriptor(),
            build_edinet_dataset_descriptor(),
            build_tdnet_dataset_descriptor(),
        ]
    )
    found = catalog.find(capability=DataCapability.DISCLOSURE)
    assert {d.dataset_id for d in found} == {"disclosure_common_core", "edinet_disclosures", "tdnet_disclosures"}


def test_tdnet_known_limitations_records_the_two_most_important_unconfirmed_items() -> None:
    """pit-auditor/skeptic-reviewer Findingの前例(EDINET D0046)を踏まえ、
    単なる参照だけでなく実際に未確認の具体的項目名がknown_limitationsへ
    反映されていることを確認する。"""
    descriptor = build_tdnet_dataset_descriptor()
    assert "DiscStatus" in descriptor.known_limitations
    assert "DiscDate" in descriptor.known_limitations or "DiscTime" in descriptor.known_limitations
    assert "TDNET_SOURCE_ONBOARDING" in descriptor.known_limitations
    assert "D0047" in descriptor.known_limitations


def test_tdnet_known_limitations_records_external_verification_provenance_caveat() -> None:
    """D0048で追加された内容: 実装がEXTERNAL_OFFICIAL_SPEC_VERIFICATION
    (ユーザー申告)に基づくものであり、Claude自身の直接確認でも真のLocal
    Real Data Validationでもないことが明示されていることを確認する。"""
    descriptor = build_tdnet_dataset_descriptor()
    assert "EXTERNAL_OFFICIAL_SPEC_VERIFICATION" in descriptor.known_limitations
    assert "D0048" in descriptor.known_limitations


def test_tdnet_notes_reference_adapter_and_normalizer_modules_that_actually_exist() -> None:
    """D0048でAdapter/Normalizerを実装した後は、Notesがその実在するModuleを
    正確に指していることを実態(Filesystem)と突き合わせて確認する
    (EDINET D0046の「実装が水増しされていないか」というskeptic-reviewer
    Findingの精神を、逆方向[過小申告になっていないか]でも適用する)。"""
    descriptor = build_tdnet_dataset_descriptor()
    assert "TdnetAdapter" in descriptor.notes
    assert "tdnet_normalize" in descriptor.notes

    providers_dir = Path(__file__).resolve().parent.parent / "lib" / "disclosures" / "providers"
    assert (providers_dir / "tdnet.py").exists()
    assert (providers_dir / "tdnet_normalize.py").exists()


def test_tdnet_notes_do_not_claim_real_local_validation_completed() -> None:
    """Adapter/Normalizerコードが存在するようになった後も、これがEXTERNAL_
    OFFICIAL_SPEC_VERIFICATIONに基づく実装であり、真のLocal Real Data
    Validation(実際のAdd-on契約済みAPI Keyでの呼び出し)ではないことを
    Notesが正確に反映していることを確認する(実装済み度の過大申告防止)。
    """
    descriptor = build_tdnet_dataset_descriptor()
    assert "EXTERNAL_OFFICIAL_SPEC_VERIFICATION" in descriptor.notes
    assert descriptor.implementation_status == ImplementationStatus.NOT_IMPLEMENTED
