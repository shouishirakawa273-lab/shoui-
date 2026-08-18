"""`lib.news.normalize`/`view`/`evidence`のPIT Test(Phase4E-2)。Test IDは
ユーザーTask仕様のNEWS-*に対応する(期待値はPhase4E-2要件から導出、実装
からのコピーではない)。NEWS-016(Historical API Response Is Not Historical
Snapshot)は既存Round(Macro/Global Market)と同じくCode Testではなく
`JAPAN_NEWS_ARCHITECTURE.md`のKnown Limitationとして文書化する(Adapter
自体が無く再現するExecution Pathが無いため)。
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from lib.evidence.model import AvailabilityBasis, AvailabilitySemantics, DataLayer, filter_usable_at
from lib.news.evidence import news_article_to_evidence
from lib.news.model import ContentAvailability, NewsArticleRecord
from lib.news.normalize import find_exact_raw_content_duplicate_groups, find_same_source_native_id_signals
from lib.news.view import news_as_of
from lib.sources.catalog import SourceAuthorityClass

RETRIEVED_AT = datetime(2026, 8, 18, 9, 10, tzinfo=UTC)


def _article(
    *,
    internal_article_id: str,
    source_native_id: str | None = None,
    headline: str = "テスト企業がテスト製品を発表",
    published_at: datetime | None = None,
    published_at_basis: AvailabilityBasis = AvailabilityBasis.UNKNOWN,
    published_date: date | None = date(2026, 8, 18),
    provider_available_at: datetime | None = None,
    provider_available_at_basis: AvailabilityBasis = AvailabilityBasis.UNKNOWN,
    retrieved_at: datetime = RETRIEVED_AT,
    entity_id: str | None = None,
) -> NewsArticleRecord:
    return NewsArticleRecord(
        internal_article_id=internal_article_id,
        source_native_id=source_native_id,
        source_id="PRTIMES",
        headline=headline,
        published_date=published_date,
        published_at=published_at,
        published_at_basis=published_at_basis,
        provider_available_at=provider_available_at,
        provider_available_at_basis=provider_available_at_basis,
        retrieved_at=retrieved_at,
        content_availability=ContentAvailability.HEADLINE_ONLY,
        entity_id=entity_id,
        normalizer_version="TEST_V1",
    )


# --- NEWS-001: Published Time Is Not Provider Availability ---


def test_news001_market_public_and_provider_available_semantics_can_disagree() -> None:
    published_at = datetime(2026, 8, 18, 9, 0, tzinfo=UTC)
    provider_available_at = datetime(2026, 8, 18, 9, 5, tzinfo=UTC)
    article = _article(
        internal_article_id="A1",
        published_at=published_at,
        published_at_basis=AvailabilityBasis.EXACT,
        provider_available_at=provider_available_at,
        provider_available_at_basis=AvailabilityBasis.EXACT,
    )
    decision_at = datetime(2026, 8, 18, 9, 2, tzinfo=UTC)  # published_atとprovider_available_atの間
    market_result = news_as_of([article], decision_at, availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT)
    provider_result = news_as_of([article], decision_at, availability_semantics=AvailabilitySemantics.PROVIDER_AVAILABLE_AT)
    assert article in market_result  # 公開時刻は過ぎている
    assert article not in provider_result  # まだこのLabからは参照可能でない


# --- NEWS-002: Unknown Provider Availability Fails Closed ---


def test_news002_unknown_provider_availability_excluded_by_default() -> None:
    article = _article(internal_article_id="A1")
    far_future = datetime(2030, 1, 1, tzinfo=UTC)
    result = news_as_of([article], far_future)
    assert article not in result


def test_news002_unknown_provider_availability_included_only_when_explicit() -> None:
    provider_available_at = datetime(2026, 8, 18, 9, 5, tzinfo=UTC)
    article = _article(
        internal_article_id="A1",
        provider_available_at=provider_available_at,
        provider_available_at_basis=AvailabilityBasis.UNKNOWN,
    )
    far_future = datetime(2030, 1, 1, tzinfo=UTC)
    result = news_as_of([article], far_future, include_unknown_availability=True)
    assert article in result


# --- NEWS-003: Retrieved At Safe Visibility ---


def test_news003_evidence_available_at_uses_retrieved_at_when_provider_available_at_unconfirmed() -> None:
    article = _article(internal_article_id="A1")
    evidence = news_article_to_evidence(
        article,
        source_authority_class=SourceAuthorityClass.COMPANY_PRIMARY,
        originating_source="TEST_ISSUER",
        delivery_provider="PRTIMES",
    )
    assert evidence.source.available_at == article.retrieved_at


def test_news003_evidence_available_at_prefers_confirmed_provider_available_at() -> None:
    provider_available_at = datetime(2026, 8, 18, 9, 5, tzinfo=UTC)
    article = _article(
        internal_article_id="A1",
        provider_available_at=provider_available_at,
        provider_available_at_basis=AvailabilityBasis.EXACT,
    )
    evidence = news_article_to_evidence(
        article,
        source_authority_class=SourceAuthorityClass.COMPANY_PRIMARY,
        originating_source="TEST_ISSUER",
        delivery_provider="PRTIMES",
    )
    assert evidence.source.available_at == provider_available_at
    assert evidence.source.available_at != article.retrieved_at


def test_news003_evidence_never_falls_back_to_published_at() -> None:
    published_at = datetime(2026, 8, 18, 8, 0, tzinfo=UTC)  # 最も早い(最も危険なFallback先)
    article = _article(
        internal_article_id="A1",
        published_at=published_at,
        published_at_basis=AvailabilityBasis.EXACT,
        provider_available_at=None,
        provider_available_at_basis=AvailabilityBasis.UNKNOWN,
    )
    evidence = news_article_to_evidence(
        article,
        source_authority_class=SourceAuthorityClass.COMPANY_PRIMARY,
        originating_source="TEST_ISSUER",
        delivery_provider="PRTIMES",
    )
    assert evidence.source.available_at != published_at
    assert evidence.source.available_at == article.retrieved_at


# --- NEWS-004/005: Date-only Publication / Timezone Unknown Does Not Guess ---


def test_news004_date_only_publication_does_not_invent_time() -> None:
    article = _article(internal_article_id="A1", published_date=date(2026, 8, 18), published_at=None)
    assert article.published_at is None
    assert article.published_date == date(2026, 8, 18)


def test_news005_naive_published_at_construction_rejected() -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        NewsArticleRecord(
            internal_article_id="A1",
            source_id="PRTIMES",
            headline="見出し",
            published_at=datetime(2026, 8, 18, 9, 0),  # tz-naive
            published_at_basis=AvailabilityBasis.EXACT,
            retrieved_at=RETRIEVED_AT,
            normalizer_version="TEST_V1",
        )


def test_news005_naive_decision_at_rejected_by_news_as_of() -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        news_as_of([], datetime(2026, 8, 18, 9, 0))


# --- NEWS-006: Mutable URL Raw Change Is Not Revision(構造確認) ---


def test_news006_news_modules_never_import_document_relationship() -> None:
    import lib.news.evidence as evidence_module
    import lib.news.model as model_module
    import lib.news.normalize as normalize_module
    import lib.news.view as view_module

    for module in (model_module, normalize_module, view_module, evidence_module):
        source = module.__file__
        assert source is not None
        text = open(source, encoding="utf-8").read()
        assert "DocumentRelationship" not in text
        assert "DuplicateRelationKind" not in text or "NewsDuplicateRelationKind" in text


def test_news006_record_has_no_supersedes_or_revision_field() -> None:
    import dataclasses

    field_names = {f.name for f in dataclasses.fields(NewsArticleRecord)}
    assert not any("supersedes" in name or "revision" in name for name in field_names)


# --- NEWS-007: Headline Similarity Is Not Duplicate ---


def test_news007_identical_headline_with_different_source_native_id_is_not_flagged() -> None:
    article_a = _article(internal_article_id="A1", source_native_id="111.1", headline="同じ見出しのテスト")
    article_b = _article(internal_article_id="A2", source_native_id="222.1", headline="同じ見出しのテスト")
    signals = find_same_source_native_id_signals([article_a, article_b])
    assert signals == []


def test_news007_no_headline_or_url_based_duplicate_function_exists_in_normalize() -> None:
    import lib.news.normalize as normalize_module

    exported = [name for name in dir(normalize_module) if not name.startswith("_")]
    for name in exported:
        assert "headline" not in name.lower()
        assert "url" not in name.lower()


# --- NEWS-008: Source-native ID Identity ---


def test_news008_same_source_native_id_is_flagged_as_duplicate_candidate() -> None:
    article_a = _article(internal_article_id="A1", source_native_id="111.1", headline="見出しA")
    article_b = _article(internal_article_id="A2", source_native_id="111.1", headline="見出しB(表記違い)")
    signals = find_same_source_native_id_signals([article_a, article_b])
    assert len(signals) == 1
    assert signals[0].article_a_id == "A1"
    assert signals[0].article_b_id == "A2"


def test_news008_empty_source_native_id_not_grouped() -> None:
    article_a = _article(internal_article_id="A1", source_native_id="")
    article_b = _article(internal_article_id="A2", source_native_id="")
    signals = find_same_source_native_id_signals([article_a, article_b])
    assert signals == []


def test_news008_exact_raw_content_duplicate_group_detected() -> None:
    payload = [{"headline": "同じ", "id": 1}, {"headline": "同じ", "id": 1}, {"headline": "別", "id": 2}]
    groups = find_exact_raw_content_duplicate_groups(payload)
    assert len(groups) == 1
    assert list(groups.values())[0] == [0, 1]


# --- NEWS-009: Missing Body Is Not Empty Fact ---


def test_news009_content_availability_distinguishes_missing_states() -> None:
    headline_only = _article(internal_article_id="A1")
    assert headline_only.content_availability == ContentAvailability.HEADLINE_ONLY
    metadata_only = NewsArticleRecord(
        internal_article_id="A2",
        source_id="PRTIMES",
        headline="見出し",
        retrieved_at=RETRIEVED_AT,
        content_availability=ContentAvailability.METADATA_ONLY,
        normalizer_version="TEST_V1",
    )
    assert metadata_only.content_availability != headline_only.content_availability


# --- NEWS-010: No Sentiment Inference ---


def test_news010_evidence_content_has_no_interpretive_language() -> None:
    article = _article(internal_article_id="A1")
    evidence = news_article_to_evidence(
        article,
        source_authority_class=SourceAuthorityClass.COMPANY_PRIMARY,
        originating_source="TEST_ISSUER",
        delivery_provider="PRTIMES",
    )
    forbidden_terms = (
        "bullish",
        "bearish",
        "buy",
        "sell",
        "good news",
        "bad news",
        "好調",
        "悪化",
        "強気",
        "弱気",
        "割安",
        "割高",
    )
    for term in forbidden_terms:
        assert term not in evidence.content.lower(), f"Evidence Contentに解釈語 '{term}' が含まれています"


# --- NEWS-011: No Event Inference(構造確認、test_news_model.pyのField Testと対応) ---


def test_news011_evidence_layer_is_normalized_not_derived_interpretation() -> None:
    article = _article(internal_article_id="A1")
    evidence = news_article_to_evidence(
        article,
        source_authority_class=SourceAuthorityClass.COMPANY_PRIMARY,
        originating_source="TEST_ISSUER",
        delivery_provider="PRTIMES",
    )
    assert evidence.layer == DataLayer.NORMALIZED
    assert evidence.ai_derived_provenance is None


# --- NEWS-012: Entity Ambiguity Fails Closed ---


def test_news012_entity_id_stays_none_when_not_explicitly_confirmed() -> None:
    article = _article(internal_article_id="A1", headline="トヨタが新製品を発表", entity_id=None)
    assert article.entity_id is None


def test_news012_entity_id_only_set_when_explicitly_supplied() -> None:
    article = _article(internal_article_id="A1", entity_id="7203")
    assert article.entity_id == "7203"


# --- NEWS-013: Future Injection ---


def test_news013_future_article_not_visible_to_past_as_of() -> None:
    future_provider_available_at = datetime(2030, 1, 1, tzinfo=UTC)
    article = _article(
        internal_article_id="A1",
        provider_available_at=future_provider_available_at,
        provider_available_at_basis=AvailabilityBasis.EXACT,
    )
    past_decision_at = datetime(2026, 8, 18, 10, 0, tzinfo=UTC)
    result = news_as_of([article], past_decision_at)
    assert article not in result


# --- NEWS-014: Determinism ---


def test_news014_same_input_produces_same_output() -> None:
    provider_available_at = datetime(2026, 8, 18, 9, 5, tzinfo=UTC)
    article = _article(
        internal_article_id="A1",
        provider_available_at=provider_available_at,
        provider_available_at_basis=AvailabilityBasis.EXACT,
    )
    decision_at = datetime(2026, 8, 18, 10, 0, tzinfo=UTC)
    result_a = news_as_of([article], decision_at)
    result_b = news_as_of([article], decision_at)
    assert result_a == result_b


# --- NEWS-015: No Backtest Wiring ---


def test_news015_news_evidence_module_never_imports_retrieval_or_filter_usable_at() -> None:
    """`lib/news/`はEvidenceを生成できるが、`lib.evidence.retrieval`
    (`retrieve_evidence()`/`filter_usable_at()`をBacktestへ接続する経路)を
    実際のImport文としては一切importしない(Phase4E-2要件§25、D0057境界
    維持)。Docstring内の説明的な言及(このRoundでは接続しない、という
    注意書き)はImport文ではないため、AST解析でImport文のみを対象にする
    (単純なTextScanだとDocstring自身の説明文に反応してしまうため)。"""
    import ast

    import lib.news.evidence as evidence_module
    import lib.news.model as model_module
    import lib.news.normalize as normalize_module
    import lib.news.view as view_module

    for module in (model_module, normalize_module, view_module, evidence_module):
        source = module.__file__
        assert source is not None
        text = open(source, encoding="utf-8").read()
        tree = ast.parse(text)
        imported_modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported_modules.add(node.module)
        assert "lib.evidence.retrieval" not in imported_modules
        assert "retrieve_evidence" not in text


def test_news015_filter_usable_at_still_works_generically_but_is_not_called_by_this_module() -> None:
    """`filter_usable_at()`自体はCommon Core関数として利用可能(構造的に
    禁止されているわけではない)が、`lib/news/`のいずれのFunctionもこれを
    呼び出さないことを、Import Scanとは別に実際の呼び出しで確認する
    (Test自身がConsumer役を果たすことで、lib/news/内部に隠れた呼び出しが
    無いことの二重確認)。"""
    article = _article(internal_article_id="A1")
    evidence = news_article_to_evidence(
        article,
        source_authority_class=SourceAuthorityClass.COMPANY_PRIMARY,
        originating_source="TEST_ISSUER",
        delivery_provider="PRTIMES",
    )
    decision_at = article.retrieved_at + timedelta(minutes=1)
    usable = filter_usable_at([evidence], decision_at)
    assert len(usable) == 1  # filter_usable_at自体は正しく動く(Common Core)が、lib/news/はこれを呼ばない
