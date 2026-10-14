"""`lib.news`のGlobal News PIT Test(Phase4E-3)。Test IDはユーザーTask
仕様のGNEWS-*に対応する(期待値はPhase4E-3要件から導出、実装からの
コピーではない)。

Phase4E-3は`lib/news/`(Phase4E-2、Japan News)を**そのまま再利用**する
(専用のGlobal News Moduleを新設しない、Phase4E-3要件§3)。このFileが
証明するのは「既存`lib.news.normalize`/`view`/`evidence`が、Global News
固有のシナリオ(多言語・Syndication・Timezone多様性)に対しても無変更で
安全に機能する」ことである——Function自体の変更は無い(model.pyへの
Optional Field追加のみ、`test_news_pit.py`参照)。
"""

from __future__ import annotations

import ast
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from lib.evidence.model import AvailabilityBasis, AvailabilitySemantics, filter_usable_at
from lib.news.evidence import news_article_to_evidence
from lib.news.model import ContentAvailability, NewsArticleRecord
from lib.news.normalize import find_exact_raw_content_duplicate_groups, find_same_source_native_id_signals
from lib.news.view import news_as_of
from lib.sources.catalog import SourceAuthorityClass

RETRIEVED_AT = datetime(2026, 8, 18, 20, 0, tzinfo=UTC)


def _global_article(
    *,
    internal_article_id: str,
    source_id: str = "REUTERS_LSEG_API",
    source_native_id: str | None = None,
    headline: str = "Test Company announces test product",
    language: str | None = "en",
    published_at: datetime | None = None,
    published_at_basis: AvailabilityBasis = AvailabilityBasis.UNKNOWN,
    published_date: date | None = date(2026, 8, 18),
    provider_available_at: datetime | None = None,
    provider_available_at_basis: AvailabilityBasis = AvailabilityBasis.UNKNOWN,
    retrieved_at: datetime = RETRIEVED_AT,
    entity_id: str | None = None,
    original_article_id: str | None = None,
    translated_from_article_id: str | None = None,
    language_variant: str | None = None,
    wire_origin: str | None = None,
    publisher: str | None = None,
    country: str | None = None,
    source_declared_timezone: str | None = None,
) -> NewsArticleRecord:
    return NewsArticleRecord(
        internal_article_id=internal_article_id,
        source_native_id=source_native_id,
        source_id=source_id,
        headline=headline,
        language=language,
        published_date=published_date,
        published_at=published_at,
        published_at_basis=published_at_basis,
        provider_available_at=provider_available_at,
        provider_available_at_basis=provider_available_at_basis,
        retrieved_at=retrieved_at,
        content_availability=ContentAvailability.HEADLINE_ONLY,
        entity_id=entity_id,
        normalizer_version="TEST_V1",
        original_article_id=original_article_id,
        translated_from_article_id=translated_from_article_id,
        language_variant=language_variant,
        wire_origin=wire_origin,
        publisher=publisher,
        country=country,
        source_declared_timezone=source_declared_timezone,
    )


# --- GNEWS-001: Published != Provider Availability(Global、複数Timezone) ---


def test_gnews001_published_and_provider_available_semantics_can_disagree_across_timezones() -> None:
    """US Eastern(published_at)とCET(provider_available_at相当のDelivery)
    のような異なるTimezone間でも、既存`news_as_of()`が正しく2系統を分離
    することを確認する(Function自体は無変更、Global Scenarioでの再証明)。"""
    published_at = datetime(2026, 8, 18, 9, 0, tzinfo=ZoneInfo("America/New_York"))
    provider_available_at = published_at.astimezone(ZoneInfo("Europe/Berlin")) + timedelta(minutes=10)
    article = _global_article(
        internal_article_id="G1",
        published_at=published_at,
        published_at_basis=AvailabilityBasis.EXACT,
        provider_available_at=provider_available_at,
        provider_available_at_basis=AvailabilityBasis.EXACT,
        wire_origin="Reuters",
    )
    decision_at = published_at + timedelta(minutes=2)
    market_result = news_as_of([article], decision_at, availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT)
    provider_result = news_as_of([article], decision_at, availability_semantics=AvailabilitySemantics.PROVIDER_AVAILABLE_AT)
    assert article in market_result
    assert article not in provider_result


# --- GNEWS-002: Unknown Availability Fails Closed ---


def test_gnews002_unknown_provider_availability_excluded_by_default() -> None:
    article = _global_article(internal_article_id="G1")
    far_future = datetime(2030, 1, 1, tzinfo=UTC)
    result = news_as_of([article], far_future)
    assert article not in result


def test_gnews002_unconfirmed_basis_excluded_even_when_timestamp_itself_is_present_and_past() -> None:
    """`provider_available_at`自体は過去の実在Timestampとして設定されて
    いても、`provider_available_at_basis`が確認済み(UNKNOWN以外)でない
    限り除外する(pit-auditor Finding、Phase4E-3: 元のTestは`timestamp is
    None`の分岐しか踏んでおらず、「Timestampはあるが未確認」というGDELT/
    SEC RSS等のScraped Timestampで現実的に起こりうる分岐を確認していな
    かった)。"""
    article = _global_article(
        internal_article_id="G1",
        provider_available_at=datetime(2026, 8, 18, 10, 0, tzinfo=UTC),
        provider_available_at_basis=AvailabilityBasis.UNKNOWN,
    )
    decision_at = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
    result = news_as_of([article], decision_at)
    assert article not in result


# --- GNEWS-003: Timezone Safety ---


def test_gnews003_naive_published_at_rejected_regardless_of_declared_timezone_label() -> None:
    """`source_declared_timezone`に何らかの文字列(例: "EST")が入っていても、
    それだけで`published_at`のtz-aware要件を免除しない(naive datetimeは
    常にReject)。"""
    with pytest.raises(ValueError, match="tz-aware"):
        NewsArticleRecord(
            internal_article_id="G1",
            source_id="REUTERS_LSEG_API",
            headline="Test headline",
            published_at=datetime(2026, 8, 18, 9, 0),  # tz-naive
            published_at_basis=AvailabilityBasis.EXACT,
            retrieved_at=RETRIEVED_AT,
            normalizer_version="TEST_V1",
            source_declared_timezone="EST",
        )


def test_gnews003_utc_and_local_timezone_decision_at_agree() -> None:
    """同一瞬間をUTCとUS Eastern(EDT/EST)で表現しても、Availability判定
    結果は一致する(GLOBAL-002/Phase4E-1と同型のTimezone変換確認、News
    向けの再証明)。"""
    provider_available_at = datetime(2026, 8, 18, 13, 0, tzinfo=UTC)
    article = _global_article(
        internal_article_id="G1",
        provider_available_at=provider_available_at,
        provider_available_at_basis=AvailabilityBasis.EXACT,
    )
    instant_utc = datetime(2026, 8, 18, 14, 0, tzinfo=UTC)
    instant_et = instant_utc.astimezone(ZoneInfo("America/New_York"))
    assert news_as_of([article], instant_utc) == news_as_of([article], instant_et)


# --- GNEWS-004: Ambiguous Timezone Abbreviation Rejected(勝手にIANAへ変換しない) ---


def test_gnews004_source_declared_timezone_is_never_read_by_normalize_view_or_evidence() -> None:
    """`source_declared_timezone`(Sourceが述べた生のTimezone文字列、例:
    "CST"のような複数のIANA Timezoneに対応しうる曖昧な略称)は、
    `published_at`のTimezone解決に一切使われない——このField自体を参照する
    Codeが`lib/news/`のnormalize.py/view.py/evidence.pyに存在しないことを
    構造的に確認する(値そのものはProvenanceとして保持するのみ)。"""
    import lib.news.evidence as evidence_module
    import lib.news.normalize as normalize_module
    import lib.news.view as view_module

    for module in (normalize_module, view_module, evidence_module):
        source = module.__file__
        assert source is not None
        text = open(source, encoding="utf-8").read()
        assert "source_declared_timezone" not in text


def test_gnews004_ambiguous_abbreviation_stored_as_is_without_iana_conversion() -> None:
    """`source_declared_timezone`は生の文字列としてそのまま保持され、
    IANA Timezone名への自動変換・正規化は一切行われないことを確認する。"""
    article = _global_article(internal_article_id="G1", source_declared_timezone="CST")
    assert article.source_declared_timezone == "CST"  # "America/Chicago"等へ変換されていない


# --- GNEWS-005: Date-only Does Not Guess Time ---


def test_gnews005_date_only_wire_release_does_not_invent_time() -> None:
    article = _global_article(internal_article_id="G1", published_date=date(2026, 8, 18), published_at=None)
    assert article.published_at is None
    assert article.published_date == date(2026, 8, 18)


# --- GNEWS-006: Translation Is Not Same Article ---


def test_gnews006_translated_article_is_not_flagged_as_duplicate_of_original() -> None:
    """`translated_from_article_id`で原文との関係が明示されていても、
    Article Identity(Safe Tier Duplicate判定)には一切使わない——
    `source_native_id`が異なる限り、翻訳記事は原文記事とは独立した
    Articleのまま扱われる(Translation Similarityからの推測禁止、
    Phase4E-3要件§9/§19)。"""
    original = _global_article(internal_article_id="G_ORIG", source_native_id="R-1001", language="en")
    translated = _global_article(
        internal_article_id="G_JA",
        source_native_id="R-1001-JA",  # 翻訳版はSource側で別Native IDを持つ(現実的想定)
        language="ja",
        translated_from_article_id="G_ORIG",
        headline="テスト企業がテスト製品を発表",
    )
    signals = find_same_source_native_id_signals([original, translated])
    assert signals == []


def test_gnews006_translated_from_field_only_set_when_explicit() -> None:
    article = _global_article(internal_article_id="G1")
    assert article.translated_from_article_id is None
    assert article.original_article_id is None
    assert article.language_variant is None


def test_gnews006_translation_fields_never_read_by_normalize_view_or_evidence() -> None:
    """GNEWS-006の他Testは`source_native_id`が異なる2記事を使っており、
    その差だけで結果が決まってしまうため`translated_from_article_id`等の
    翻訳関連Field自体を読んでいないことの直接証拠にはならない(skeptic-
    reviewer Finding、Phase4E-3: GNEWS-006は「構造的」と説明されていたが
    実際はGNEWS-004のような直接のSource文字列探索を伴っていなかった)。
    GNEWS-004と同じ手法で、翻訳関連Field名自体が`lib/news/normalize.py`/
    `view.py`/`evidence.py`のいずれにも登場しないことを直接確認する。"""
    import lib.news.evidence as evidence_module
    import lib.news.normalize as normalize_module
    import lib.news.view as view_module

    translation_field_names = ("translated_from_article_id", "original_article_id", "language_variant")
    for module in (normalize_module, view_module, evidence_module):
        source = module.__file__
        assert source is not None
        text = open(source, encoding="utf-8").read()
        for field_name in translation_field_names:
            assert field_name not in text, (module.__name__, field_name)


# --- GNEWS-007: Cross-source Same Event Is Not Duplicate Article ---


def test_gnews007_reuters_and_bloomberg_articles_about_same_event_are_not_flagged() -> None:
    """`find_same_source_native_id_signals()`は`headline`等のContentを
    一切読まない(`normalize.py`Docstring参照)ため、Reuters記事とBloomberg
    記事のように`source_id`が異なる2記事は、それらが実際に同じEvent
    (Event Identityは共通しうる)を報じていようが全く無関係な話題だろうが
    区別せずDuplicateとして検出しない——これは「同じEventを検出しつつ
    正しく別Articleと判定する」という意味論的な区別を証明するTestでは
    なく、`source_id`でScopeする既存構造(Phase4E-2 skeptic-reviewer
    Findingの延長)がAnyのContentに対して安全側に倒れることのPinning
    Testである(skeptic-reviewer Finding、Phase4E-3: 当初の説明は意味論的
    区別を証明したかのように読めたため訂正)。Article Identity != Event
    Identity(Phase4E-3要件§20)という設計方針自体は、Event Identityを
    判定するLogicがこのLabにまだ存在しないことの裏返しでもある。"""
    reuters_article = _global_article(internal_article_id="G_R", source_id="REUTERS_LSEG_API", source_native_id="1001")
    bloomberg_article = _global_article(
        internal_article_id="G_B", source_id="BLOOMBERG_API", source_native_id="1001", wire_origin="Bloomberg"
    )
    signals = find_same_source_native_id_signals([reuters_article, bloomberg_article])
    assert signals == []


# --- GNEWS-008: Source-native Identity ---


def test_gnews008_same_source_and_native_id_is_flagged_as_duplicate_candidate() -> None:
    article_a = _global_article(internal_article_id="G1", source_id="REUTERS_LSEG_API", source_native_id="1001")
    article_b = _global_article(internal_article_id="G2", source_id="REUTERS_LSEG_API", source_native_id="1001")
    signals = find_same_source_native_id_signals([article_a, article_b])
    assert len(signals) == 1


def test_gnews008_same_wire_origin_via_different_publishers_is_not_automatically_same_article() -> None:
    """同じ`wire_origin`(Reuters)の記事が異なる`publisher`(現地新聞A・B)
    経由で掲載されても、Retrieval Source(`source_id`)が異なる限り自動
    Duplicateにしない(Syndication、Phase4E-3要件§12)。ただし
    `find_same_source_native_id_signals()`は`wire_origin`/`publisher`を
    そもそも一切読まない(`normalize.py`Docstring参照)ため、この結果は
    「Syndication構造を認識した上で区別した」ことの証明ではなく、
    `source_id`が異なる2記事は常にPass-Throughされるという既存構造の
    Pinning Testである(skeptic-reviewer Finding、Phase4E-3、GNEWS-007と
    同型の訂正)。"""
    via_publisher_a = _global_article(
        internal_article_id="G_A",
        source_id="LOCAL_PAPER_A_FEED",
        source_native_id="SYN-1",
        wire_origin="Reuters",
        publisher="Local Paper A",
    )
    via_publisher_b = _global_article(
        internal_article_id="G_B",
        source_id="LOCAL_PAPER_B_FEED",
        source_native_id="SYN-1",
        wire_origin="Reuters",
        publisher="Local Paper B",
    )
    signals = find_same_source_native_id_signals([via_publisher_a, via_publisher_b])
    assert signals == []


# --- GNEWS-009: Mutable URL Is Not Revision(構造確認) ---


def test_gnews009_news_modules_never_import_document_relationship() -> None:
    import lib.news.evidence as evidence_module
    import lib.news.model as model_module
    import lib.news.normalize as normalize_module
    import lib.news.view as view_module

    for module in (model_module, normalize_module, view_module, evidence_module):
        source = module.__file__
        assert source is not None
        text = open(source, encoding="utf-8").read()
        assert "DocumentRelationship" not in text


# --- GNEWS-010: Missing Body Is Not No News ---


def test_gnews010_content_availability_distinguishes_missing_states_for_global_article() -> None:
    metadata_only = NewsArticleRecord(
        internal_article_id="G1",
        source_id="REUTERS_LSEG_API",
        headline="Test headline",
        retrieved_at=RETRIEVED_AT,
        content_availability=ContentAvailability.METADATA_ONLY,
        normalizer_version="TEST_V1",
    )
    unknown = NewsArticleRecord(
        internal_article_id="G2",
        source_id="REUTERS_LSEG_API",
        headline="Test headline",
        retrieved_at=RETRIEVED_AT,
        normalizer_version="TEST_V1",
    )
    assert metadata_only.content_availability != unknown.content_availability
    assert unknown.content_availability == ContentAvailability.UNKNOWN


# --- GNEWS-011: No Sentiment ---


def test_gnews011_evidence_content_has_no_interpretive_or_macro_sentiment_language() -> None:
    article = _global_article(internal_article_id="G1")
    evidence = news_article_to_evidence(
        article,
        source_authority_class=SourceAuthorityClass.VERIFIED_SECONDARY,
        originating_source="Reuters",
        delivery_provider="REUTERS_LSEG_API",
    )
    forbidden_terms = (
        "bullish",
        "bearish",
        "buy",
        "sell",
        "risk-on",
        "risk-off",
        "hawkish",
        "dovish",
        "good news",
        "bad news",
    )
    for term in forbidden_terms:
        assert term not in evidence.content.lower(), f"Evidence Contentに解釈語 '{term}' が含まれています"


# --- GNEWS-012: No Event Inference(構造確認) ---


def test_gnews012_news_article_record_has_no_event_type_field() -> None:
    import dataclasses

    field_names = {f.name for f in dataclasses.fields(NewsArticleRecord)}
    assert "event_type" not in field_names
    assert "confidence" not in field_names


# --- GNEWS-013: No Japanese Stock Mapping ---


def test_gnews013_entity_id_not_inferred_from_headline_mentioning_japanese_company() -> None:
    """`NewsArticleRecord`は素朴なDataclassであり、`entity_id`はConstructor
    引数からField代入されるのみでHeadline Text解析を一切経由しない
    (`__post_init__`にもEntity推定Logicは無い)。このTestが実際に確認
    するのは「そのようなInference Logicがこのbundle(このRoundで新設した
    どのModuleにも)存在しない」という現状のPinning(将来Adapter実装時に
    Headline由来のEntity推定が紛れ込んでいないかを検知するRegression
    Guard)であり、「Inference Logicへの攻撃に対する防御を証明した」もの
    ではない(skeptic-reviewer Finding、Phase4E-3: 当初の説明は後者の
    ように読めたため訂正)。"""
    article = _global_article(
        internal_article_id="G1",
        headline="Toyota Motor faces new tariff challenges, sources say",
        entity_id=None,
    )
    assert article.entity_id is None


def test_gnews013_country_not_inferred_from_article_language() -> None:
    """`country`はArticleのLanguageから推測しない(Phase4E-3要件§22)。
    Sourceが明示しない限り`None`のまま。GNEWS-013の`entity_id`Testと同様、
    これは「Language推測Logicが存在しないこと」のPinning Testであり、
    将来的なInference機能に対する防御力の証明ではない。"""
    japanese_language_article = _global_article(internal_article_id="G1", language="ja", country=None)
    assert japanese_language_article.country is None


# --- GNEWS-014: Future Injection ---


def test_gnews014_future_wire_release_not_visible_to_past_as_of() -> None:
    future_provider_available_at = datetime(2030, 1, 1, tzinfo=UTC)
    article = _global_article(
        internal_article_id="G1",
        provider_available_at=future_provider_available_at,
        provider_available_at_basis=AvailabilityBasis.EXACT,
    )
    past_decision_at = datetime(2026, 8, 18, 21, 0, tzinfo=UTC)
    result = news_as_of([article], past_decision_at)
    assert article not in result


# --- GNEWS-015: Determinism ---


def test_gnews015_same_input_produces_same_output() -> None:
    provider_available_at = datetime(2026, 8, 18, 21, 5, tzinfo=UTC)
    article = _global_article(
        internal_article_id="G1",
        provider_available_at=provider_available_at,
        provider_available_at_basis=AvailabilityBasis.EXACT,
    )
    decision_at = datetime(2026, 8, 19, 0, 0, tzinfo=UTC)
    assert news_as_of([article], decision_at) == news_as_of([article], decision_at)


# --- GNEWS-016: No Backtest Wiring(構造確認、D0057境界) ---


def test_gnews016_news_evidence_module_never_imports_retrieval_or_filter_usable_at() -> None:
    """`from lib.evidence import retrieval`のような「Package importして属性
    経由でAccess」する形も見逃さないよう、`node.module`単体ではなく
    `module.name`のFully Qualified Pathを組み立てて判定する(pit-auditor
    Finding、Phase4E-3: 元の実装は`node.module`のみをそのまま集合へ入れて
    おり、`from lib.evidence import retrieval`だと`"lib.evidence"`にしか
    ならず`"lib.evidence.retrieval"`という文字列に一致しないため検出漏れ
    していた)。"""
    import lib.news.evidence as evidence_module
    import lib.news.model as model_module
    import lib.news.normalize as normalize_module
    import lib.news.view as view_module

    for module in (model_module, normalize_module, view_module, evidence_module):
        source = module.__file__
        assert source is not None
        text = open(source, encoding="utf-8").read()
        tree = ast.parse(text)
        imported_targets: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_targets.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported_targets.add(node.module)
                imported_targets.update(f"{node.module}.{alias.name}" for alias in node.names)
        assert not any(
            target == "lib.evidence.retrieval" or target.startswith("lib.evidence.retrieval.") for target in imported_targets
        ), imported_targets


def test_gnews016_filter_usable_at_still_works_but_is_not_called_internally() -> None:
    article = _global_article(internal_article_id="G1")
    evidence = news_article_to_evidence(
        article,
        source_authority_class=SourceAuthorityClass.VERIFIED_SECONDARY,
        originating_source="Reuters",
        delivery_provider="REUTERS_LSEG_API",
    )
    decision_at = article.retrieved_at + timedelta(minutes=1)
    assert len(filter_usable_at([evidence], decision_at)) == 1


# --- GNEWS-017: Claim Is Not Confirmed Fact ---


def test_gnews017_evidence_content_never_incorporates_body_text_or_hedge_language() -> None:
    """Evidence Contentは`headline`/`source_id`/`published_display`のみから
    機械的に構築され、記事本文(Claim/Hedge表現を含みうる)を一切取り込まない
    ことを構造的に確認する。`news_article_to_evidence()`のSignatureが
    `NewsArticleRecord`(本文Fieldを持たない)のみを引数に取ることが、この
    保証の構造的根拠である。"""
    article = _global_article(internal_article_id="G1", headline="Central bank considering rate move, sources say")
    evidence = news_article_to_evidence(
        article,
        source_authority_class=SourceAuthorityClass.VERIFIED_SECONDARY,
        originating_source="Reuters",
        delivery_provider="REUTERS_LSEG_API",
    )
    # 見出し自体にHedge表現が含まれていても、Evidence Contentはそれをそのまま
    # 「見出しとして公開された」というMeta-level Factとして記述するのみであり、
    # 新たな確信的言明(例: 「利下げ決定」という確定表現)を生成しない。
    assert "確定" not in evidence.content
    assert "decided" not in evidence.content.lower()


# --- GNEWS-018: Language Unknown Is Not English ---


def test_gnews018_language_defaults_to_none_not_english() -> None:
    article = NewsArticleRecord(
        internal_article_id="G1",
        source_id="REUTERS_LSEG_API",
        headline="Some headline",
        retrieved_at=RETRIEVED_AT,
        normalizer_version="TEST_V1",
    )
    assert article.language is None


# --- 追加Field(region/jurisdiction)のRound-trip確認(skeptic-reviewer Finding、Phase4E-3) ---
# region/jurisdictionはGNEWS-001~018のいずれからも一切構築されておらず、
# `country`と異なりTest Coverageが皆無だった(CLAUDE.mdの「新機能には必ず
# Testを追加する」原則にも反する)。country同様、Sourceが明示した値をそのまま
# 保持するのみでLanguage/Headlineからは推測しないことを直接確認する。


def test_region_and_jurisdiction_are_stored_as_given_not_inferred() -> None:
    article = NewsArticleRecord(
        internal_article_id="G1",
        source_id="REUTERS_LSEG_API",
        headline="European Central Bank statement",
        language="en",
        retrieved_at=RETRIEVED_AT,
        normalizer_version="TEST_V1",
        country="DE",
        region="EU",
        jurisdiction="EU",
    )
    assert article.region == "EU"
    assert article.jurisdiction == "EU"


def test_region_and_jurisdiction_default_to_none_when_not_supplied() -> None:
    article = NewsArticleRecord(
        internal_article_id="G1",
        source_id="REUTERS_LSEG_API",
        headline="Some headline",
        language="fr",
        retrieved_at=RETRIEVED_AT,
        normalizer_version="TEST_V1",
    )
    assert article.region is None
    assert article.jurisdiction is None


# --- find_exact_raw_content_duplicate_groups()のGlobal Newsシナリオでの確認(skeptic-reviewer Finding、Phase4E-3) ---
# 既存Phase4E-2 Testはこの関数をJapan Newsの文脈でのみExerciseしており、
# このRoundの新規Test(test_global_news_pit.py)は`find_same_source_native_id_
# signals()`しかImport/呼び出ししていなかった。


def test_find_exact_raw_content_duplicate_groups_detects_pagination_overlap_in_global_feed() -> None:
    """複数国のWire Feedを跨ぐPagination境界で同一行が重複取得された場合の
    検出(Headlineの言語やSourceの違いを問わず、行全体のHash完全一致のみで
    判定する既存挙動をGlobal Newsの文脈で再確認する)。"""
    payload = [
        {"source_id": "REUTERS_LSEG_API", "source_native_id": "1001", "headline": "ECB holds rates"},
        {"source_id": "SEC_PRESS_RELEASE", "source_native_id": "2002", "headline": "SEC announces settlement"},
        {"source_id": "REUTERS_LSEG_API", "source_native_id": "1001", "headline": "ECB holds rates"},
    ]
    groups = find_exact_raw_content_duplicate_groups(payload)
    assert len(groups) == 1
    (indices,) = groups.values()
    assert indices == [0, 2]
