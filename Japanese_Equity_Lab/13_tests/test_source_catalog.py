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
