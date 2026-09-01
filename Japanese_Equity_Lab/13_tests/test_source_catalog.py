"""Phase3D(D0040): Data Catalogのテスト。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from lib.sources.catalog import (
    DataCapability,
    DatasetDescriptor,
    ImplementationStatus,
    PrimaryOrSecondary,
    SourceAuthorityClass,
    SourceCatalog,
    SourceMetadata,
)


def test_source_metadata_requires_tz_aware_datetimes() -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        SourceMetadata(
            source_id="s1",
            source_type="TDNET",
            provider_name="TDnet",
            source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
            primary_or_secondary=PrimaryOrSecondary.PRIMARY,
            retrieved_at=datetime(2024, 1, 1),  # tz無し
            published_at=None,
            available_at=datetime(2024, 1, 1, tzinfo=UTC),
        )


def _dataset(dataset_id: str, capability: DataCapability, **kwargs: object) -> DatasetDescriptor:
    return DatasetDescriptor(
        dataset_id=dataset_id,
        source_id="jquants",
        capability=capability,
        authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        **kwargs,  # type: ignore[arg-type]
    )


def test_catalog_find_by_capability() -> None:
    catalog = SourceCatalog(
        [
            _dataset("jquants_bars", DataCapability.MARKET_PRICE),
            _dataset("edinet_disclosures", DataCapability.DISCLOSURE),
        ]
    )
    results = catalog.find(capability=DataCapability.MARKET_PRICE)
    assert {d.dataset_id for d in results} == {"jquants_bars"}


def test_catalog_find_by_code_includes_code_agnostic_datasets() -> None:
    catalog = SourceCatalog(
        [
            DatasetDescriptor(
                dataset_id="ds_7203",
                source_id="edinet",
                capability=DataCapability.DISCLOSURE,
                authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
                applicable_codes=("7203",),
            ),
            DatasetDescriptor(
                dataset_id="ds_topix",
                source_id="jquants",
                capability=DataCapability.MARKET_PRICE,
                authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
                applicable_codes=None,  # 銘柄非依存
            ),
        ]
    )
    results = catalog.find(code="7203")
    assert {d.dataset_id for d in results} == {"ds_7203", "ds_topix"}
    results_other_code = catalog.find(code="6758")
    assert {d.dataset_id for d in results_other_code} == {"ds_topix"}


def test_catalog_rejects_duplicate_dataset_id() -> None:
    catalog = SourceCatalog([_dataset("dup", DataCapability.NEWS)])
    with pytest.raises(ValueError, match="dup"):
        catalog.register(_dataset("dup", DataCapability.NEWS))


def test_catalog_default_implementation_status_is_not_implemented() -> None:
    """CatalogにDatasetとして記述されていることと実接続済みであることを混同しない。"""
    dataset = _dataset("future_source", DataCapability.MACRO)
    assert dataset.implementation_status == ImplementationStatus.NOT_IMPLEMENTED


# --- D0042: SourceAuthorityClassは単純なスコア/順位ではない ---


def test_source_authority_class_is_not_an_int_enum() -> None:
    """PRIMARY_OFFICIAL=100点、SOCIAL=10点のような数値スコアリングに使える
    IntEnumではなく、文字列カテゴリ(StrEnum)であることを構造的に確認する。"""
    assert not issubclass(SourceAuthorityClass, int)
    for member in SourceAuthorityClass:
        assert isinstance(member.value, str)


def test_source_catalog_module_defines_no_authority_scoring_function() -> None:
    """`SourceAuthorityClass`を数値スコアへ変換する関数/定数(例: authority_score,
    AUTHORITY_WEIGHTS等)がこのモジュールに存在しないことを構造的に確認する
    (StrEnumはstrを継承するため`<`は文字列としての大小比較になり、信頼度の
    順序を意味しない。数値化する仕組み自体を作らないことが本来の保証)。"""
    import lib.sources.catalog as catalog_module

    forbidden_substrings = ("score", "weight", "rank")
    suspicious_names = [name for name in dir(catalog_module) if any(bad in name.lower() for bad in forbidden_substrings)]
    assert suspicious_names == []


# --- D0042: Originating SourceとDelivery Providerの分離 ---


def test_source_metadata_distinguishes_originating_source_from_delivery_provider() -> None:
    """EDINET由来の情報をJ-Quants経由で取得した場合、原典(originating_source)と
    配送経路(delivery_provider)を別々に保持できる。"""
    metadata = SourceMetadata(
        source_id="s1",
        source_type="DISCLOSURE",
        provider_name="J-Quants",
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        primary_or_secondary=PrimaryOrSecondary.PRIMARY,
        retrieved_at=datetime(2024, 1, 1, tzinfo=UTC),
        published_at=datetime(2024, 1, 1, tzinfo=UTC),
        available_at=datetime(2024, 1, 1, tzinfo=UTC),
        originating_source="EDINET",
        delivery_provider="JQUANTS",
    )
    assert metadata.originating_source == "EDINET"
    assert metadata.delivery_provider == "JQUANTS"
    assert metadata.originating_source != metadata.delivery_provider


def test_source_metadata_originating_source_and_delivery_provider_default_to_none() -> None:
    """既存Schemaとの後方互換: 未設定でも構築できる(破壊的変更ではない)。"""
    metadata = SourceMetadata(
        source_id="s1",
        source_type="TDNET",
        provider_name="TDnet",
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        primary_or_secondary=PrimaryOrSecondary.PRIMARY,
        retrieved_at=datetime(2024, 1, 1, tzinfo=UTC),
        published_at=datetime(2024, 1, 1, tzinfo=UTC),
        available_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    assert metadata.originating_source is None
    assert metadata.delivery_provider is None


def test_direct_edinet_source_has_matching_originating_source_and_delivery_provider() -> None:
    """直接EDINET APIから取得した場合は、原典と配送経路が一致する。"""
    metadata = SourceMetadata(
        source_id="s2",
        source_type="DISCLOSURE",
        provider_name="EDINET",
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        primary_or_secondary=PrimaryOrSecondary.PRIMARY,
        retrieved_at=datetime(2024, 1, 1, tzinfo=UTC),
        published_at=datetime(2024, 1, 1, tzinfo=UTC),
        available_at=datetime(2024, 1, 1, tzinfo=UTC),
        originating_source="EDINET",
        delivery_provider="EDINET_DIRECT",
    )
    assert metadata.originating_source == "EDINET"
    assert metadata.delivery_provider == "EDINET_DIRECT"
