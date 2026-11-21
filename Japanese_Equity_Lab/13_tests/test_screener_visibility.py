"""Step 3 可視性判定の合成データテスト。実APIには一切接続しない。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from lib.evidence.model import AvailabilityBasis, AvailabilitySemantics, RevisionHistory, SourceVersion
from lib.screener.visibility import visible_versions

DECISION_AT = datetime(2026, 11, 21, 15, 30, tzinfo=UTC)


def _version(
    vid: str,
    *,
    published: datetime | None,
    available: datetime,
    basis: AvailabilityBasis = AvailabilityBasis.UNKNOWN,
) -> SourceVersion:
    return SourceVersion(
        source_record_id="S1",
        source_version_id=vid,
        value="100",
        available_at=available,
        retrieved_at=DECISION_AT,
        availability_basis=basis,
        published_at=published,
    )


def _history(*versions: SourceVersion) -> RevisionHistory:
    return RevisionHistory(series_id="S1", versions=tuple(versions))


def test_market_public_at_excludes_future_publications() -> None:
    past = _version("v1", published=datetime(2026, 5, 1, tzinfo=UTC), available=datetime(2026, 5, 1, tzinfo=UTC))
    future = _version("v2", published=datetime(2026, 12, 1, tzinfo=UTC), available=datetime(2026, 12, 1, tzinfo=UTC))

    result = visible_versions(_history(past, future), DECISION_AT, availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT)

    assert [v.source_version_id for v in result] == ["v1"]


def test_market_public_at_drops_versions_with_no_publication_time() -> None:
    """公開時刻が不明なVersionは「いつ知り得たか」が決まらないので含めない。"""
    known = _version("v1", published=datetime(2026, 5, 1, tzinfo=UTC), available=datetime(2026, 5, 1, tzinfo=UTC))
    unknown = _version("v2", published=None, available=datetime(2026, 5, 2, tzinfo=UTC))

    result = visible_versions(
        _history(known, unknown), DECISION_AT, availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT
    )

    assert [v.source_version_id for v in result] == ["v1"]


def test_versions_are_returned_oldest_first() -> None:
    newer = _version("v2", published=datetime(2026, 8, 1, tzinfo=UTC), available=datetime(2026, 8, 1, tzinfo=UTC))
    older = _version("v1", published=datetime(2026, 5, 1, tzinfo=UTC), available=datetime(2026, 5, 1, tzinfo=UTC))

    result = visible_versions(_history(newer, older), DECISION_AT, availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT)

    assert [v.source_version_id for v in result] == ["v1", "v2"]


def test_provider_available_at_excludes_unknown_basis_by_default() -> None:
    """Phase4Aでは basis が常に UNKNOWN。既定で空になるのは安全側の仕様。"""
    v = _version("v1", published=None, available=datetime(2026, 5, 1, tzinfo=UTC))

    default = visible_versions(_history(v), DECISION_AT, availability_semantics=AvailabilitySemantics.PROVIDER_AVAILABLE_AT)
    opted_in = visible_versions(
        _history(v),
        DECISION_AT,
        availability_semantics=AvailabilitySemantics.PROVIDER_AVAILABLE_AT,
        include_unknown_availability=True,
    )

    assert default == []
    assert [x.source_version_id for x in opted_in] == ["v1"]


def test_provider_available_at_keeps_known_basis() -> None:
    v = _version(
        "v1",
        published=None,
        available=datetime(2026, 5, 1, tzinfo=UTC),
        basis=AvailabilityBasis.EXACT,
    )

    result = visible_versions(_history(v), DECISION_AT, availability_semantics=AvailabilitySemantics.PROVIDER_AVAILABLE_AT)

    assert [x.source_version_id for x in result] == ["v1"]


def test_naive_decision_at_is_rejected() -> None:
    v = _version("v1", published=datetime(2026, 5, 1, tzinfo=UTC), available=datetime(2026, 5, 1, tzinfo=UTC))

    with pytest.raises(ValueError, match="timezone-aware"):
        visible_versions(
            _history(v), datetime(2026, 11, 21, 15, 30), availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT
        )
