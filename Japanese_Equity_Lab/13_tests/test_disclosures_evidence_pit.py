"""Disclosure Common Core Evidence PIT Bugfix(D0050): `disclosure_document_to_evidence()`の
`source.available_at`が`market_public_at`へFallbackしていたBugの回帰テスト。

## Root Cause

旧実装は`available_at = document.market_public_at or document.retrieved_at`
としていた。`lib.fundamentals.evidence.disclosure_metric_to_evidence()`が
D0049で修正したのと同型のBugであり、D0049時点ではCommon Core側
(このModule)は未修正のまま残っていた(D0049 §4-4/§5-2でFollow-upとして
記録済み)。

`market_public_at`(市場公表時刻、A系統)は通常`provider_available_at`
(Provider経由で実際に参照可能になった時刻、B系統)より**早い**ため、これを
`available_at`へ代入すると、実際にはまだ研究所側で取得可能でなかった時点を
「利用可能だった」と誤認する(Future Leakage)。

## Fix

`DisclosureDocument`は`provider_available_at`/`provider_available_at_basis`
をFieldとして持つ(Fundamentalsの`DisclosureEnvelope`には無いField)。
したがって`source.available_at`は、`provider_available_at_basis`が
`UNKNOWN`でなければその値を、そうでなければ`document.retrieved_at`
(Observed Factとしての下限)を使う。`market_public_at`へは決して
Fallbackしない。
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from lib.disclosures.evidence import disclosure_document_to_evidence
from lib.disclosures.model import DisclosureDocument
from lib.evidence.model import AvailabilityBasis
from lib.sources.catalog import SourceAuthorityClass


def _build_document(
    *,
    market_public_at: datetime | None,
    retrieved_at: datetime,
    provider_available_at: datetime | None = None,
    provider_available_at_basis: AvailabilityBasis = AvailabilityBasis.UNKNOWN,
) -> DisclosureDocument:
    return DisclosureDocument(
        internal_document_id="DOC_TEST_1",
        source_document_id="D1",
        entity_id="7203",
        title="決算短信〔IFRS〕(連結)",
        originating_source="TDnet",
        delivery_provider="J-Quants",
        market_public_at=market_public_at,
        market_public_at_basis=(AvailabilityBasis.EXACT if market_public_at is not None else AvailabilityBasis.UNKNOWN),
        provider_available_at=provider_available_at,
        provider_available_at_basis=provider_available_at_basis,
        retrieved_at=retrieved_at,
    )


# --- A. market_public_atがretrieved_atより早い場合(provider_available_at未確認) ---


def test_available_at_uses_retrieved_at_not_market_public_at_when_provider_available_at_unknown() -> None:
    """Root Causeそのものの再現: market_public_at=15:00、retrieved_at=15:06、
    provider_available_atはUNKNOWNの場合、available_atは15:06(retrieved_at)
    であり、15:00(market_public_at)ではないことを確認する。"""
    market_public_at = datetime(2026, 8, 17, 15, 0, tzinfo=UTC)
    retrieved_at = datetime(2026, 8, 17, 15, 6, tzinfo=UTC)
    document = _build_document(market_public_at=market_public_at, retrieved_at=retrieved_at)

    evidence = disclosure_document_to_evidence(document, source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL)

    assert evidence.source.published_at == market_public_at
    assert evidence.source.available_at == retrieved_at
    assert evidence.source.available_at != market_public_at


def test_available_at_never_falls_back_to_market_public_at_when_market_public_at_is_none() -> None:
    retrieved_at = datetime(2026, 8, 17, 15, 6, tzinfo=UTC)
    document = _build_document(market_public_at=None, retrieved_at=retrieved_at)

    evidence = disclosure_document_to_evidence(document, source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL)

    assert evidence.source.published_at is None
    assert evidence.source.available_at == retrieved_at


@pytest.mark.parametrize(
    ("market_public_at", "retrieved_at"),
    [
        (datetime(2026, 8, 17, 15, 0, tzinfo=UTC), datetime(2026, 8, 17, 15, 6, tzinfo=UTC)),
        (None, datetime(2026, 8, 17, 15, 6, tzinfo=UTC)),
        (datetime(2026, 8, 17, 9, 0, tzinfo=UTC), datetime(2026, 8, 18, 9, 0, tzinfo=UTC)),
    ],
)
def test_available_at_always_equals_retrieved_at_when_provider_available_at_unknown(
    market_public_at: datetime | None, retrieved_at: datetime
) -> None:
    document = _build_document(market_public_at=market_public_at, retrieved_at=retrieved_at)
    evidence = disclosure_document_to_evidence(document, source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL)
    assert evidence.source.available_at == retrieved_at


# --- B. provider_available_atが確認済みの場合はそれを優先する(市場公表時刻より遅い設定でも尊重) ---


def test_available_at_uses_confirmed_provider_available_at_when_basis_is_not_unknown() -> None:
    """`provider_available_at_basis`がUNKNOWNでなければ、`retrieved_at`ではなく
    確認済みの`provider_available_at`を使う(将来Providerが確認済み値を
    提供するようになった場合への前方互換性)。"""
    market_public_at = datetime(2026, 8, 17, 15, 0, tzinfo=UTC)
    provider_available_at = datetime(2026, 8, 17, 15, 2, tzinfo=UTC)
    retrieved_at = datetime(2026, 8, 17, 15, 6, tzinfo=UTC)
    document = _build_document(
        market_public_at=market_public_at,
        retrieved_at=retrieved_at,
        provider_available_at=provider_available_at,
        provider_available_at_basis=AvailabilityBasis.EXACT,
    )

    evidence = disclosure_document_to_evidence(document, source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL)

    assert evidence.source.available_at == provider_available_at
    assert evidence.source.available_at != retrieved_at
    assert evidence.source.available_at != market_public_at


def test_available_at_ignores_provider_available_at_when_basis_is_unknown_even_if_value_present() -> None:
    """`provider_available_at`に値が入っていても、`basis=UNKNOWN`なら
    信頼せず`retrieved_at`を使う(値の存在だけで信頼しない、Basis必須)。"""
    market_public_at = datetime(2026, 8, 17, 15, 0, tzinfo=UTC)
    provider_available_at = datetime(2026, 8, 17, 15, 2, tzinfo=UTC)
    retrieved_at = datetime(2026, 8, 17, 15, 6, tzinfo=UTC)
    document = _build_document(
        market_public_at=market_public_at,
        retrieved_at=retrieved_at,
        provider_available_at=provider_available_at,
        provider_available_at_basis=AvailabilityBasis.UNKNOWN,
    )

    evidence = disclosure_document_to_evidence(document, source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL)

    assert evidence.source.available_at == retrieved_at
    assert evidence.source.available_at != provider_available_at


# --- C. as_of between market_public_at and retrieved_at(B系統相当のEvidence Availability) ---


def test_evidence_is_not_usable_at_decision_at_between_market_public_at_and_retrieved_at() -> None:
    """decision_at=15:03(market_public_at=15:00とretrieved_at=15:06の間)では、
    `EvidenceRecord.is_usable_at()`がFalseを返すことを確認する(旧Bugでは
    available_at=15:00とされ、15:03時点で誤ってTrueになっていた)。"""
    market_public_at = datetime(2026, 8, 17, 15, 0, tzinfo=UTC)
    retrieved_at = datetime(2026, 8, 17, 15, 6, tzinfo=UTC)
    document = _build_document(market_public_at=market_public_at, retrieved_at=retrieved_at)
    evidence = disclosure_document_to_evidence(document, source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL)

    decision_at_between = datetime(2026, 8, 17, 15, 3, tzinfo=UTC)
    assert evidence.is_usable_at(decision_at_between) is False

    decision_at_after_retrieval = datetime(2026, 8, 17, 15, 6, tzinfo=UTC)
    assert evidence.is_usable_at(decision_at_after_retrieval) is True

    decision_at_before_market_public = datetime(2026, 8, 17, 14, 59, tzinfo=UTC)
    assert evidence.is_usable_at(decision_at_before_market_public) is False


# --- D. EDINET/TDnetいずれも現状provider_available_atは常にUNKNOWNのため、常にretrieved_atを使う ---


def test_edinet_style_document_uses_retrieved_at_since_provider_available_at_stays_unknown() -> None:
    """EDINET Normalizer(`edinet_normalize.py`)は`provider_available_at`を
    常に`None`/`UNKNOWN`のまま構築するため、EDINET由来のDocumentも常に
    `retrieved_at`が使われることを確認する(EDINET Adapter/Normalizer自体は
    変更していない、既存の`document.market_public_at=None`という実際の
    出力を模して確認する)。"""
    retrieved_at = datetime(2026, 8, 17, 15, 6, tzinfo=UTC)
    document = _build_document(market_public_at=None, retrieved_at=retrieved_at)
    evidence = disclosure_document_to_evidence(document, source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL)
    assert evidence.source.available_at == retrieved_at


def test_tdnet_style_document_uses_retrieved_at_not_market_public_at_despite_exact_value() -> None:
    """TDnet Normalizer(`tdnet_normalize.py`)は`market_public_at`の値自体は
    `DiscDate`+`DiscTime`から構築するが、`provider_available_at`は常に
    `None`/`UNKNOWN`のままである(D0048)。したがってTDnet由来のDocumentも
    常に`retrieved_at`が使われることを確認する。"""
    market_public_at = datetime(2026, 8, 17, 15, 0, tzinfo=UTC)
    retrieved_at = datetime(2026, 8, 17, 15, 6, tzinfo=UTC)
    document = _build_document(market_public_at=market_public_at, retrieved_at=retrieved_at)
    evidence = disclosure_document_to_evidence(document, source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL)
    assert evidence.source.available_at == retrieved_at
    assert evidence.source.available_at != market_public_at
