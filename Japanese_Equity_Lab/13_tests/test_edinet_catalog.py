"""Phase4B-2: EDINETのSource Catalog登録(`build_edinet_dataset_descriptor`)のテスト。"""

from __future__ import annotations

from lib.disclosures.catalog import build_disclosure_common_core_dataset_descriptor, build_edinet_dataset_descriptor
from lib.sources.catalog import DataCapability, ImplementationStatus, SourceAuthorityClass, SourceCatalog


def test_edinet_registered_under_disclosure_capability_as_connected_but_pit_unavailable() -> None:
    """D0046追記: Local Real Data Validation完了によりCONNECTEDへ更新した。
    ただしPIT意味論(market_public_at/provider_available_at)は依然未確認
    のため、pit_availableはFalseのまま(「取得できる」≠「PIT安全に使える」)。"""
    catalog = SourceCatalog([build_edinet_dataset_descriptor()])
    found = catalog.find(capability=DataCapability.DISCLOSURE)
    assert [d.dataset_id for d in found] == ["edinet_disclosures"]
    assert found[0].implementation_status == ImplementationStatus.CONNECTED
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


def test_edinet_known_limitations_references_onboarding_report_and_key_unconfirmed_items() -> None:
    """pit-auditor Finding(D0046追記): 単なる文字列存在チェックはほぼ無意味
    (中身が正しいかを検証しない)なので、実際にEDINET_SOURCE_ONBOARDING.mdで
    未確認と判定された具体的な項目名がknown_limitationsへ反映されていることまで
    確認する(空欄のまま参照だけ書く、という劣化を検知できるようにする)。"""
    descriptor = build_edinet_dataset_descriptor()
    assert "submitDateTime" in descriptor.known_limitations
    assert "document_kind" in descriptor.known_limitations
    assert "entity_id" in descriptor.known_limitations
    assert "D0046" in descriptor.known_limitations


def test_edinet_pit_available_false_is_documentation_only_not_a_runtime_gate() -> None:
    """pit-auditor Finding(D0046追記): `pit_available`は`SourceCatalog`のどの
    コードからも読まれておらず、実行時の防御にはなっていない(Catalog全体に
    共通する既存の設計上の制約であり、このPhaseで新規導入した問題ではない)。"""
    import lib.sources.catalog as catalog_module

    source = catalog_module.__file__
    assert source is not None
    with open(source, encoding="utf-8") as f:
        text = f.read()
    # SourceCatalog.find()はpit_availableを絞り込み条件として一切参照しない
    # (dataset_id/capability/code/country/sector/implementation_statusのみ)。
    assert "pit_available" not in text.split("class SourceCatalog:")[1]


def test_edinet_pit_safety_comes_from_availability_basis_unknown_not_from_no_construction() -> None:
    """skeptic-reviewer Finding(D0046追記): 上のTestの旧Docstringは
    「DisclosureDocument/EvidenceRecordをEDINETデータから一切構築していない」
    という理由でPIT安全と説明していたが、これは`edinet_normalize.py`の追加に
    より事実と異なる(実際にDisclosureDocumentを構築している)。正しい理由は、
    構築されたDocumentの`market_public_at_basis`/`provider_available_at_basis`
    が常に`AvailabilityBasis.UNKNOWN`であり、`disclosures_as_of()`が
    タイムスタンプ`None`のDocumentを比較前に除外することによってPIT安全な
    経路(Normalizer -> disclosures_as_of())が守られている、という点を
    明示的に回帰確認する(直接`disclosure_document_to_evidence()`等の
    非PIT-aware経路を素通しした場合はこの限りではないことは、`lib.
    disclosures.evidence`のDocstring自体が別途警告している)。"""
    from datetime import UTC, datetime

    from lib.disclosures.providers.edinet_normalize import parse_edinet_documents_list_payload
    from lib.evidence.model import AvailabilityBasis

    body = {
        "metadata": {"status": "200", "resultset": {"count": 1}},
        "results": [{"docID": "D1", "submitDateTime": "2024-05-08 15:30"}],
    }
    (document, _meta) = parse_edinet_documents_list_payload(body, retrieved_at=datetime(2026, 8, 17, tzinfo=UTC))[0]
    assert document.market_public_at_basis == AvailabilityBasis.UNKNOWN
    assert document.provider_available_at_basis == AvailabilityBasis.UNKNOWN
    assert document.market_public_at is None
    assert document.provider_available_at is None
