"""Phase4B-1(D0045): As-of View(`lib.disclosures.view.disclosures_as_of`)のテスト。

外部呼び出しと分離する(D0042 Offline原則)ため、事前に構築済みの
`DisclosureDocument`のみを使い、一切の外部呼び出しを行わない。
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from lib.disclosures.model import DisclosureDocument
from lib.disclosures.view import disclosures_as_of
from lib.evidence.model import AvailabilityBasis, AvailabilitySemantics

_JST = ZoneInfo("Asia/Tokyo")
_RETRIEVED_AT = datetime(2026, 1, 1, tzinfo=UTC)


def _doc(
    internal_document_id: str,
    *,
    market_public_at: datetime | None,
    market_public_at_basis: AvailabilityBasis = AvailabilityBasis.EXACT,
    provider_available_at: datetime | None = None,
    provider_available_at_basis: AvailabilityBasis = AvailabilityBasis.UNKNOWN,
) -> DisclosureDocument:
    return DisclosureDocument(
        internal_document_id=internal_document_id,
        title=f"title-{internal_document_id}",
        retrieved_at=_RETRIEVED_AT,
        market_public_at=market_public_at,
        market_public_at_basis=market_public_at_basis,
        provider_available_at=provider_available_at,
        provider_available_at_basis=provider_available_at_basis,
    )


# 同一会社・同日、時刻違いの2文書(§9「Publication after Market Close」相当)。
_DOC_1400 = _doc("DOC_1400", market_public_at=datetime(2024, 5, 8, 14, 0, tzinfo=_JST))
_DOC_1530 = _doc("DOC_1530", market_public_at=datetime(2024, 5, 8, 15, 30, tzinfo=_JST))


# --- Test 1/2/3: Future除外・同日Later Time除外・同日Earlier Time許可 ---


def test_same_day_earlier_time_document_included() -> None:
    result = disclosures_as_of(
        [_DOC_1400, _DOC_1530],
        datetime(2024, 5, 8, 14, 0, tzinfo=_JST),
        availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT,
    )
    assert {d.internal_document_id for d in result} == {"DOC_1400"}


def test_same_day_later_time_document_excluded() -> None:
    """decision_at=15:00は同日でも15:30公表の文書をまだ見えない(単純Date比較禁止)。"""
    result = disclosures_as_of(
        [_DOC_1400, _DOC_1530],
        datetime(2024, 5, 8, 15, 0, tzinfo=_JST),
        availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT,
    )
    assert {d.internal_document_id for d in result} == {"DOC_1400"}


def test_both_documents_visible_once_decision_at_passes_both_times() -> None:
    result = disclosures_as_of(
        [_DOC_1400, _DOC_1530],
        datetime(2024, 5, 8, 16, 0, tzinfo=_JST),
        availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT,
    )
    assert {d.internal_document_id for d in result} == {"DOC_1400", "DOC_1530"}


def test_future_document_excluded_before_any_publication() -> None:
    result = disclosures_as_of(
        [_DOC_1400, _DOC_1530],
        datetime(2024, 5, 8, 0, 0, tzinfo=_JST),
        availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT,
    )
    assert result == []


# --- Test 4: tz-aware必須 ---


def test_disclosures_as_of_requires_tz_aware_decision_at() -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        disclosures_as_of([_DOC_1400], datetime(2024, 5, 8, 14, 0))


# --- Test 6/7: provider_available_at UNKNOWN Basisはfallbackしない、A系統/B系統の違い ---


def test_provider_available_at_semantics_default_excludes_unknown_basis() -> None:
    """market_public_atが確認できていても、provider_available_at_basisが
    UNKNOWNのままならB系統(既定)からは見えない(D0043の原則をDocumentへ継承)。"""
    doc = _doc(
        "DOC_UNKNOWN_AVAIL",
        market_public_at=datetime(2024, 5, 8, 14, 0, tzinfo=_JST),
        provider_available_at=datetime(2024, 5, 8, 14, 0, tzinfo=_JST),
        provider_available_at_basis=AvailabilityBasis.UNKNOWN,
    )
    result = disclosures_as_of([doc], datetime(2024, 9, 1, tzinfo=UTC))  # 既定 = PROVIDER_AVAILABLE_AT
    assert result == []


def test_provider_available_at_semantics_explicit_opt_in_includes_unknown_basis() -> None:
    doc = _doc(
        "DOC_UNKNOWN_AVAIL",
        market_public_at=datetime(2024, 5, 8, 14, 0, tzinfo=_JST),
        provider_available_at=datetime(2024, 5, 8, 14, 0, tzinfo=_JST),
        provider_available_at_basis=AvailabilityBasis.UNKNOWN,
    )
    result = disclosures_as_of(
        [doc],
        datetime(2024, 9, 1, tzinfo=UTC),
        include_unknown_availability=True,
    )
    assert {d.internal_document_id for d in result} == {"DOC_UNKNOWN_AVAIL"}


def test_market_public_at_semantics_and_provider_available_at_semantics_differ() -> None:
    """同じDocument集合でも、A系統(確認済みのmarket_public_at)は見えるが、
    B系統の既定(provider_available_atのBasisがUNKNOWN)は見えない、という
    振る舞いの違いが実際に発生することを確認する。"""
    doc = _doc(
        "DOC_A_VS_B",
        market_public_at=datetime(2024, 5, 8, 14, 0, tzinfo=_JST),
        provider_available_at=datetime(2024, 5, 8, 14, 0, tzinfo=_JST),
        provider_available_at_basis=AvailabilityBasis.UNKNOWN,
    )
    decision_at = datetime(2024, 9, 1, tzinfo=UTC)
    a_semantics = disclosures_as_of([doc], decision_at, availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT)
    b_semantics_default = disclosures_as_of([doc], decision_at)
    assert len(a_semantics) == 1
    assert b_semantics_default == []


# --- Test 27: Append-only(将来のDocument追加が過去のas_of Viewを変えない) ---


def test_adding_future_document_does_not_change_earlier_as_of_view() -> None:
    decision_at = datetime(2024, 5, 8, 14, 30, tzinfo=_JST)
    view_before = disclosures_as_of([_DOC_1400], decision_at, availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT)
    view_after_adding_future_doc = disclosures_as_of(
        [_DOC_1400, _DOC_1530], decision_at, availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT
    )
    assert {d.internal_document_id for d in view_before} == {d.internal_document_id for d in view_after_adding_future_doc}
    assert {d.internal_document_id for d in view_before} == {"DOC_1400"}


def test_documents_without_market_public_at_are_never_included_under_market_public_semantics() -> None:
    doc_unknown_time = _doc("DOC_NO_TIME", market_public_at=None, market_public_at_basis=AvailabilityBasis.UNKNOWN)
    result = disclosures_as_of(
        [doc_unknown_time],
        datetime(2030, 1, 1, tzinfo=UTC),
        availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT,
    )
    assert result == []
