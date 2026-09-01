"""Fundamentals A系統(MARKET_PUBLIC_AT)Bridge: `fundamentals_as_of()`の
選定Logicと`source_version_to_evidence_market_public_at()`のTest(D0072/
D0074 Follow-up、Fundamentals Availability Architecture Gapの最小解消)。

B系統(`disclosure_metric_to_evidence()`、`available_at=retrieved_at`)は
変更しないため、既存`test_fundamentals_evidence_pit.py`はそのまま維持する。
このFileはA系統専用の新規Testのみを持つ。
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from lib.evidence.model import AvailabilityBasis, AvailabilitySemantics, RevisionHistory, SourceVersion
from lib.fundamentals.evidence import MARKET_PUBLIC_AT_SOURCE_TYPE, source_version_to_evidence_market_public_at
from lib.fundamentals.view import fundamentals_as_of

_SERIES = "7203|sales|CURRENT_FISCAL_YEAR|2Q|CONSOLIDATED|IFRS"


def _version(*, published_at: datetime | None, value: str = "100", source_version_id: str = "V1") -> SourceVersion:
    return SourceVersion(
        source_record_id=_SERIES,
        source_version_id=source_version_id,
        value=value,
        available_at=datetime(2026, 8, 16, tzinfo=UTC),  # B系統相当の下限、A系統では使わない
        retrieved_at=datetime(2026, 8, 16, tzinfo=UTC),
        availability_basis=AvailabilityBasis.UNKNOWN,  # B系統は既定でこのまま除外される(既存挙動、無変更)
        published_at=published_at,
    )


def test_a_path_before_disclosure_is_unavailable() -> None:
    """as_ofが開示(market_public_at)より前の場合、A系統selectionはNoneを
    返す(未来の開示を過去へ漏らさない)。"""
    v = _version(published_at=datetime(2024, 11, 6, 4, 55, tzinfo=UTC))
    history = RevisionHistory(series_id=_SERIES, versions=(v,))
    result = fundamentals_as_of(
        {_SERIES: history},
        datetime(2024, 11, 1, tzinfo=UTC),
        availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT,
    )
    assert result[_SERIES] is None


def test_a_path_after_disclosure_is_usable() -> None:
    """as_ofが開示以降であれば、A系統selectionがそのVersionを返し、
    Bridge経由でavailable_at=published_atのEvidenceになることを確認する。"""
    published_at = datetime(2024, 11, 6, 4, 55, tzinfo=UTC)
    v = _version(published_at=published_at)
    history = RevisionHistory(series_id=_SERIES, versions=(v,))
    result = fundamentals_as_of(
        {_SERIES: history},
        datetime(2024, 11, 15, tzinfo=UTC),
        availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT,
    )
    assert result[_SERIES] is v

    evidence = source_version_to_evidence_market_public_at(v, entity_code="7203")
    assert evidence.source.source_type == MARKET_PUBLIC_AT_SOURCE_TYPE
    assert evidence.source.available_at == published_at
    assert evidence.is_usable_at(datetime(2024, 11, 15, tzinfo=UTC))
    assert not evidence.is_usable_at(datetime(2024, 11, 1, tzinfo=UTC))


def test_future_revision_does_not_leak() -> None:
    """同一Seriesに複数Versionがある場合、as_of時点でまだ公表されていない
    将来のRevisionは選ばれない(古いVersionのみが選定される)。"""
    old = _version(published_at=datetime(2023, 11, 1, tzinfo=UTC), value="90", source_version_id="V_OLD")
    new = _version(published_at=datetime(2024, 11, 6, tzinfo=UTC), value="100", source_version_id="V_NEW")
    history = RevisionHistory(series_id=_SERIES, versions=(old, new))

    result = fundamentals_as_of(
        {_SERIES: history},
        datetime(2024, 1, 1, tzinfo=UTC),  # newの公表前
        availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT,
    )
    assert result[_SERIES] is old


def test_future_correction_does_not_leak() -> None:
    """訂正(Correction)相当のVersionも、通常のRevisionと同じ`published_at`
    Chronologyで扱われ、as_of以降に公表されたものは漏れない。"""
    original = _version(published_at=datetime(2024, 11, 6, tzinfo=UTC), value="100", source_version_id="V_ORIG")
    correction = _version(published_at=datetime(2024, 12, 20, tzinfo=UTC), value="95", source_version_id="V_CORR")
    history = RevisionHistory(series_id=_SERIES, versions=(original, correction))

    result = fundamentals_as_of(
        {_SERIES: history},
        datetime(2024, 11, 15, tzinfo=UTC),  # correction公表前
        availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT,
    )
    assert result[_SERIES] is original


def test_unknown_market_public_at_is_rejected() -> None:
    """`published_at=None`(market_public_at_basis=UNKNOWN相当)のVersionを
    直接Bridgeへ渡した場合、fail closedで拒否する(値を推測しない)。"""
    v = _version(published_at=None)
    with pytest.raises(ValueError, match="UNKNOWN"):
        source_version_to_evidence_market_public_at(v, entity_code="7203")


def test_unknown_market_public_at_is_excluded_by_fundamentals_as_of() -> None:
    """`fundamentals_as_of(availability_semantics=MARKET_PUBLIC_AT)`自体も、
    published_at=NoneのVersionを候補から除外することを確認する(Bridgeの
    Guardが実際には到達しないGuardであることの裏付け)。"""
    unknown = _version(published_at=None, source_version_id="V_UNKNOWN")
    history = RevisionHistory(series_id=_SERIES, versions=(unknown,))
    result = fundamentals_as_of(
        {_SERIES: history},
        datetime(2026, 1, 1, tzinfo=UTC),
        availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT,
    )
    assert result[_SERIES] is None
