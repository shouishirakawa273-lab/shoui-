"""Phase3D(D0040)/Phase4 Architecture Cleanup(D0042): Evidence Model
(Type/Layer/PIT/Revision/Availability Semantics/Value Availability)のテスト。"""

from __future__ import annotations

import copy
from datetime import UTC, datetime

import pytest
from lib.evidence.model import (
    AiDerivedProvenance,
    AvailabilityBasis,
    AvailabilitySemantics,
    DataLayer,
    EvidenceRecord,
    EvidenceType,
    RevisionHistory,
    SourceVersion,
    ValueAvailability,
    filter_usable_at,
)
from lib.sources.catalog import DataCapability, PrimaryOrSecondary, SourceAuthorityClass, SourceMetadata


def _source(
    *, available_at: datetime, published_at: datetime | None = None, retrieved_at: datetime | None = None
) -> SourceMetadata:
    return SourceMetadata(
        source_id="s1",
        source_type="TDNET",
        provider_name="TDnet",
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        primary_or_secondary=PrimaryOrSecondary.PRIMARY,
        retrieved_at=retrieved_at or available_at,
        published_at=published_at,
        available_at=available_at,
    )


def _record(evidence_id: str, evidence_type: EvidenceType, *, available_at: datetime) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        evidence_type=evidence_type,
        layer=DataLayer.NORMALIZED,
        capability=DataCapability.DISCLOSURE,
        content="テスト内容",
        source=_source(available_at=available_at),
    )


# --- Test 2: FACTとOPINIONが混在しない ---


def test_fact_and_opinion_types_remain_distinct_not_collapsed() -> None:
    fact = _record("E_FACT", EvidenceType.FACT, available_at=datetime(2024, 1, 1, tzinfo=UTC))
    opinion = _record("E_OPINION", EvidenceType.OPINION, available_at=datetime(2024, 1, 1, tzinfo=UTC))
    pool = {fact.evidence_id: fact, opinion.evidence_id: opinion}
    assert pool["E_FACT"].evidence_type == EvidenceType.FACT
    assert pool["E_OPINION"].evidence_type == EvidenceType.OPINION
    assert pool["E_FACT"].evidence_type != pool["E_OPINION"].evidence_type


# --- Test 3: published_atより前のDecisionでEvidenceが取得されない ---


def test_evidence_not_usable_before_available_at() -> None:
    record = _record("E1", EvidenceType.FACT, available_at=datetime(2024, 6, 1, 15, 0, tzinfo=UTC))
    assert record.is_usable_at(datetime(2024, 5, 31, 23, 0, tzinfo=UTC)) is False
    assert record.is_usable_at(datetime(2024, 6, 1, 15, 0, tzinfo=UTC)) is True


# --- Test 4: 後日retrieved_atした古い情報でもavailable_at以前には使用できない ---


def test_recent_retrieval_does_not_make_old_evidence_usable_earlier() -> None:
    """retrieved_at(取得日)が最近でも、available_at(当時の入手可能時刻)基準でPIT判定する。"""
    source = _source(
        available_at=datetime(2020, 1, 10, tzinfo=UTC),
        published_at=datetime(2020, 1, 10, tzinfo=UTC),
        retrieved_at=datetime(2026, 8, 16, tzinfo=UTC),  # 今日取得した
    )
    record = EvidenceRecord(
        evidence_id="E_OLD",
        evidence_type=EvidenceType.FACT,
        layer=DataLayer.NORMALIZED,
        capability=DataCapability.DISCLOSURE,
        content="2020年の情報",
        source=source,
    )
    assert record.is_usable_at(datetime(2020, 1, 5, tzinfo=UTC)) is False
    assert record.is_usable_at(datetime(2020, 1, 10, tzinfo=UTC)) is True


def test_filter_usable_at_excludes_future_evidence() -> None:
    past = _record("E_PAST", EvidenceType.FACT, available_at=datetime(2024, 1, 1, tzinfo=UTC))
    future = _record("E_FUTURE", EvidenceType.FACT, available_at=datetime(2024, 6, 1, tzinfo=UTC))
    usable = filter_usable_at([past, future], datetime(2024, 3, 1, tzinfo=UTC))
    assert usable == (past,)


# --- Test 5: RevisionされたMacro値について後のRevisionを過去DecisionへLeakしない ---


def _version(
    version_id: str, value: str, *, available_at: datetime, basis: AvailabilityBasis = AvailabilityBasis.EXACT
) -> SourceVersion:
    return SourceVersion(
        source_record_id="GDP_2024Q1",
        source_version_id=version_id,
        value=value,
        available_at=available_at,
        retrieved_at=available_at,
        availability_basis=basis,
    )


def test_revision_history_as_of_does_not_leak_future_revision() -> None:
    history = RevisionHistory(
        series_id="GDP_2024Q1",
        versions=(
            _version("v1", "1.0%", available_at=datetime(2024, 5, 1, tzinfo=UTC)),
            _version("v2", "1.5%", available_at=datetime(2024, 8, 1, tzinfo=UTC)),  # 後日の改訂
        ),
    )
    at_first_release = history.as_of(datetime(2024, 6, 1, tzinfo=UTC))
    after_revision = history.as_of(datetime(2024, 9, 1, tzinfo=UTC))
    before_any_release = history.as_of(datetime(2024, 1, 1, tzinfo=UTC))
    assert at_first_release is not None and at_first_release.value == "1.0%"
    assert after_revision is not None and after_revision.value == "1.5%"
    assert before_any_release is None


def test_revision_history_latest_is_not_pit_safe_and_documented_as_such() -> None:
    """`latest()`はPIT非考慮であり、過去Decisionへそのまま流用してはならない(as_of()を使う)。"""
    history = RevisionHistory(
        series_id="GDP_2024Q1",
        versions=(
            _version("v1", "1.0%", available_at=datetime(2024, 5, 1, tzinfo=UTC)),
            _version("v2", "1.5%", available_at=datetime(2024, 8, 1, tzinfo=UTC)),
        ),
    )
    assert history.latest() is not None and history.latest().value == "1.5%"  # type: ignore[union-attr]
    # as_of()なら2024-06-01時点ではv2(将来の改訂)は見えない
    assert history.as_of(datetime(2024, 6, 1, tzinfo=UTC)).value == "1.0%"  # type: ignore[union-attr]


def test_revision_history_excludes_unknown_availability_basis_by_default() -> None:
    """availability_basis=UNKNOWNのVersionは、available_atをpublished_at等から
    推測補完していない証として、既定ではPIT利用可能とみなさない。"""
    history = RevisionHistory(
        series_id="S1",
        versions=(_version("v1", "unclear", available_at=datetime(2024, 1, 1, tzinfo=UTC), basis=AvailabilityBasis.UNKNOWN),),
    )
    assert history.as_of(datetime(2024, 6, 1, tzinfo=UTC)) is None
    # 明示的に許容した場合のみ使える(オプトイン)。
    included = history.as_of(datetime(2024, 6, 1, tzinfo=UTC), include_unknown_availability=True)
    assert included is not None and included.value == "unclear"


def test_source_version_requires_tz_aware_datetimes() -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        SourceVersion(
            source_record_id="s",
            source_version_id="v1",
            value="x",
            available_at=datetime(2024, 1, 1),  # tz無し
            retrieved_at=datetime(2024, 1, 1, tzinfo=UTC),
        )


# --- AI-Derived Provenance: DerivedはRaw Factを上書きしない(layerの強制) ---


def test_ai_derived_provenance_requires_derived_layer() -> None:
    provenance = AiDerivedProvenance(
        model_provider="anthropic",
        model_name="test-model",
        generated_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    with pytest.raises(ValueError, match="DERIVED"):
        EvidenceRecord(
            evidence_id="E1",
            evidence_type=EvidenceType.INTERPRETATION,
            layer=DataLayer.NORMALIZED,  # DERIVEDではない
            capability=DataCapability.NEWS,
            content="AI要約",
            source=_source(available_at=datetime(2024, 1, 1, tzinfo=UTC)),
            ai_derived_provenance=provenance,
        )


def test_ai_derived_provenance_allowed_with_derived_layer() -> None:
    provenance = AiDerivedProvenance(
        model_provider="anthropic",
        model_name="test-model",
        input_evidence_ids=("E_RAW_1",),
        generated_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    record = EvidenceRecord(
        evidence_id="E_DERIVED",
        evidence_type=EvidenceType.INTERPRETATION,
        layer=DataLayer.DERIVED,
        capability=DataCapability.NEWS,
        content="AI要約",
        source=_source(available_at=datetime(2024, 1, 1, tzinfo=UTC)),
        ai_derived_provenance=provenance,
    )
    assert record.ai_derived_provenance is not None
    assert record.ai_derived_provenance.input_evidence_ids == ("E_RAW_1",)


# --- Test 1: Raw PayloadがNormalized変換後も改変されない ---


def test_normalizing_raw_payload_does_not_mutate_original_dict() -> None:
    raw_payload = {"headline": "テスト見出し", "value": "120億円", "code": "7203"}
    raw_payload_copy = copy.deepcopy(raw_payload)

    # Normalized EvidenceRecordを構築する(値は参照するだけで、rawを書き換えない)。
    EvidenceRecord(
        evidence_id="E1",
        evidence_type=EvidenceType.FACT,
        layer=DataLayer.NORMALIZED,
        capability=DataCapability.DISCLOSURE,
        content=raw_payload["headline"],
        source=_source(available_at=datetime(2024, 1, 1, tzinfo=UTC)),
        related_codes=(raw_payload["code"],),
    )
    assert raw_payload == raw_payload_copy


# --- D0042: market_public_at相当とprovider_available_at相当を区別可能 ---


def test_published_at_and_available_at_can_diverge_for_provider_delay() -> None:
    """15:30に会社が決算公表(published_at=market_public_at相当)、J-Quants Light
    経由では18:00に取得可能になった(available_at=provider_available_at相当)、
    という状況を別々のFieldで表現できる。PIT判定はavailable_at基準。"""
    market_public_at = datetime(2024, 6, 1, 15, 30, tzinfo=UTC)
    provider_available_at = datetime(2024, 6, 1, 18, 0, tzinfo=UTC)
    source = SourceMetadata(
        source_id="s1",
        source_type="TDNET",
        provider_name="J-Quants",
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        primary_or_secondary=PrimaryOrSecondary.PRIMARY,
        retrieved_at=datetime(2024, 6, 1, 18, 3, tzinfo=UTC),
        published_at=market_public_at,
        available_at=provider_available_at,
    )
    record = EvidenceRecord(
        evidence_id="E1",
        evidence_type=EvidenceType.FACT,
        layer=DataLayer.NORMALIZED,
        capability=DataCapability.DISCLOSURE,
        content="決算公表",
        source=source,
    )
    # Reproducible System Simulation(B系統): provider_available_at(18:00)基準。
    assert record.is_usable_at(datetime(2024, 6, 1, 16, 0, tzinfo=UTC)) is False
    assert record.is_usable_at(datetime(2024, 6, 1, 18, 0, tzinfo=UTC)) is True
    # Market Information Study(A系統)で使う場合はpublished_atを別途参照する。
    assert record.source.published_at == market_public_at
    assert record.source.published_at != record.source.available_at


def test_availability_semantics_distinguishes_two_kinds_of_pit_research() -> None:
    assert AvailabilitySemantics.MARKET_PUBLIC_AT != AvailabilitySemantics.PROVIDER_AVAILABLE_AT


# --- D0042/D0043: NULL/NOT_APPLICABLEを0へ潰さないSchema Contract(Phase4A) ---


def test_value_availability_not_applicable_is_distinct_from_zero_and_missing() -> None:
    """会計基準上存在しない指標(NOT_APPLICABLE)と、単にProvider側で空
    (MISSING_OR_UNSPECIFIED)は別概念であり、どちらも数値の0とは異なる
    (Phase4A Fundamental Schema Contract、D0043)。"""
    assert ValueAvailability.NOT_APPLICABLE != ValueAvailability.MISSING_OR_UNSPECIFIED
    assert ValueAvailability.NOT_APPLICABLE != 0
    assert ValueAvailability.MISSING_OR_UNSPECIFIED != 0
    assert ValueAvailability.UNKNOWN != 0
    assert ValueAvailability.PRESENT != 0


# --- D0042: Revision Historyへrevision_reasonを追加(Fundamentalへの拡張準備) ---


def test_source_version_records_revision_reason() -> None:
    version = SourceVersion(
        source_record_id="EARNINGS_2024Q1",
        source_version_id="v2",
        value="120億円",
        available_at=datetime(2024, 8, 1, tzinfo=UTC),
        retrieved_at=datetime(2024, 8, 1, tzinfo=UTC),
        availability_basis=AvailabilityBasis.EXACT,
        supersedes_version_id="v1",
        is_correction=True,
        revision_reason="会社側の入力ミス訂正",
    )
    assert version.revision_reason == "会社側の入力ミス訂正"
    assert version.is_correction is True
    assert version.supersedes_version_id == "v1"
