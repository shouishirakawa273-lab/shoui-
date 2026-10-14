"""`lib.news.model.NewsArticleRecord`/Enum群のTest(Phase4E-2)。"""

from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime

import pytest
from lib.evidence.model import AvailabilityBasis
from lib.news.model import ContentAvailability, NewsArticleRecord

RETRIEVED_AT = datetime(2026, 8, 18, 9, 0, tzinfo=UTC)


def _base_article(**overrides: object) -> NewsArticleRecord:
    base: dict[str, object] = {
        "internal_article_id": "NEWS_1",
        "source_native_id": "12345.1",
        "source_id": "PRTIMES",
        "headline": "テスト企業がテスト製品を発表",
        "language": "ja",
        "canonical_url": "https://example.com/article/1",
        "published_date": date(2026, 8, 18),
        "published_at": None,
        "published_at_basis": AvailabilityBasis.UNKNOWN,
        "provider_available_at": None,
        "provider_available_at_basis": AvailabilityBasis.UNKNOWN,
        "retrieved_at": RETRIEVED_AT,
        "updated_at": None,
        "content_availability": ContentAvailability.HEADLINE_ONLY,
        "raw_snapshot_ref": None,
        "entity_id": None,
        "source_field": None,
        "normalizer_version": "TEST_V1",
        "provenance_id": None,
    }
    base.update(overrides)
    return NewsArticleRecord(**base)


def test_internal_article_id_required_non_empty() -> None:
    with pytest.raises(ValueError, match="internal_article_id"):
        _base_article(internal_article_id="")


def test_source_id_required_non_empty() -> None:
    with pytest.raises(ValueError, match="source_id"):
        _base_article(source_id="")


def test_headline_required_non_empty() -> None:
    with pytest.raises(ValueError, match="headline"):
        _base_article(headline="")


def test_retrieved_at_requires_tz_aware() -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        _base_article(retrieved_at=datetime(2026, 8, 18, 9, 0))


def test_published_at_requires_tz_aware_when_present() -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        _base_article(published_at=datetime(2026, 8, 18, 10, 0))


def test_published_at_basis_forced_unknown_when_value_absent() -> None:
    with pytest.raises(ValueError, match="published_at"):
        _base_article(published_at=None, published_at_basis=AvailabilityBasis.EXACT)


def test_provider_available_at_requires_tz_aware_when_present() -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        _base_article(provider_available_at=datetime(2026, 8, 18, 10, 0))


def test_provider_available_at_basis_forced_unknown_when_value_absent() -> None:
    with pytest.raises(ValueError, match="provider_available_at"):
        _base_article(provider_available_at=None, provider_available_at_basis=AvailabilityBasis.EXACT)


def test_updated_at_requires_tz_aware_when_present() -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        _base_article(updated_at=datetime(2026, 8, 19, 10, 0))


def test_source_native_id_defaults_to_none_not_guessed() -> None:
    article = _base_article(source_native_id=None)
    assert article.source_native_id is None


def test_canonical_url_is_not_required_and_not_used_as_identity_field_alone() -> None:
    """`canonical_url`はOptionalであり、Article Identityの必須要素ではない
    (Phase4E-2要件§11)。`source_native_id`が無くても構築できることを確認。"""
    article = _base_article(source_native_id=None, canonical_url=None)
    assert article.internal_article_id == "NEWS_1"


def test_published_date_only_is_accepted_without_published_at() -> None:
    """日付のみ確認できる場合、published_atをNoneのまま日付のみ保持できる
    (Phase4E-2要件§12、時刻を推測しない)。"""
    article = _base_article(published_date=date(2026, 8, 18), published_at=None)
    assert article.published_date == date(2026, 8, 18)
    assert article.published_at is None


def test_entity_id_defaults_to_none() -> None:
    article = _base_article()
    assert article.entity_id is None


def test_content_availability_defaults_to_unknown_not_full_text() -> None:
    base: dict[str, object] = {
        "internal_article_id": "NEWS_2",
        "source_id": "PRTIMES",
        "headline": "見出し",
        "retrieved_at": RETRIEVED_AT,
        "normalizer_version": "TEST_V1",
    }
    article = NewsArticleRecord(**base)
    assert article.content_availability == ContentAvailability.UNKNOWN


def test_content_availability_values_are_distinct() -> None:
    assert {c.value for c in ContentAvailability} == {
        "FULL_TEXT",
        "HEADLINE_ONLY",
        "METADATA_ONLY",
        "REFERENCE_ONLY",
        "UNKNOWN",
    }


def test_news_article_record_has_no_event_type_field() -> None:
    """`NewsArticleRecord`はEvent抽出後を前提とする`event_type`Fieldを持たない
    (`lib.evidence.news.NewsEvent`との境界、Phase4E-2要件§24、model.py
    Docstring参照)。"""
    field_names = {f.name for f in dataclasses.fields(NewsArticleRecord)}
    assert "event_type" not in field_names
    assert "confidence" not in field_names
    assert "affected_sectors" not in field_names
    assert "affected_codes" not in field_names
