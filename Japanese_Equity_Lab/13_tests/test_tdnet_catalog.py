"""Phase4B-3(D0047): TDnetのSource Catalog登録(`build_tdnet_dataset_descriptor`)のテスト。

このPhaseではAdapter/Normalizerを一切実装していない(TDNET_SOURCE_
ONBOARDING.md参照、公式資料への接続がブロックされ、タスク上最重要の
訂正/削除/PIT意味論いずれも裏付けが得られなかったため)。Testは
Catalog登録の正しさ(NOT_IMPLEMENTED・pit_available=False)と、既存
Dataset(EDINET/Disclosure Common Core)との共存のみを対象とする。
"""

from __future__ import annotations

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


def test_tdnet_notes_do_not_claim_any_adapter_code_exists() -> None:
    """このPhaseで`lib/disclosures/providers/tdnet.py`(Adapter/Normalizer)を
    実装していないことをNotesが正確に反映していることを確認する
    (実装が水増しされていないことの回帰確認)。

    Notes文字列中の「未実装」という部分文字列の存在確認だけでは、Notesの
    他の箇所が誤って実装済みであるかのように書き換えられてもTestが検知
    できない(Tautologyに近いというskeptic-reviewer Finding)。実際に
    `lib/disclosures/providers/tdnet.py`がFilesystem上に存在しないことを
    直接確認することで、Notesの文言ではなく実態そのものを検証する。
    """
    from pathlib import Path

    descriptor = build_tdnet_dataset_descriptor()
    assert "未実装" in descriptor.notes

    providers_dir = Path(__file__).resolve().parent.parent / "lib" / "disclosures" / "providers"
    assert not (providers_dir / "tdnet.py").exists()
