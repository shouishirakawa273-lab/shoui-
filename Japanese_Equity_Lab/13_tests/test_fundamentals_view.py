"""Phase4A(D0043): As-of Fundamental View(`lib.fundamentals.view`)のテスト。

外部API取得と分析を分離する(D0042 Offline原則)ため、ここでは事前に構築済みの
`RevisionHistory`だけを使い、一切の外部呼び出しを行わない。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from lib.evidence.model import AvailabilityBasis, AvailabilitySemantics, RevisionHistory, SourceVersion
from lib.fundamentals.normalize import build_revision_histories, parse_financial_summary_payload
from lib.fundamentals.view import as_of_by_semantics, fundamentals_as_of

_FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "financial_summary_v2.json"
_RETRIEVED_AT = datetime(2026, 1, 1, tzinfo=UTC)


def _load_payload() -> list[dict[str, object]]:
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))["data"]


def _toyota_op_forecast_series_id(histories: dict[str, RevisionHistory]) -> str:
    return next(sid for sid in histories if sid.startswith("7203|operating_profit_current_year_forecast|CURRENT_FISCAL_YEAR|FY|"))


@pytest.fixture
def toyota_histories() -> dict[str, RevisionHistory]:
    envelopes, metrics = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    return build_revision_histories(envelopes, metrics)


# --- Test 16: As-of Fundamental View(Revision前後で値が変わる、市場公表基準) ---


def test_as_of_view_reflects_forecast_before_and_after_revision_market_public_at(
    toyota_histories: dict[str, RevisionHistory],
) -> None:
    sid = _toyota_op_forecast_series_id(toyota_histories)
    before = fundamentals_as_of(
        toyota_histories, datetime(2024, 6, 1, tzinfo=UTC), availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT
    )
    after = fundamentals_as_of(
        toyota_histories, datetime(2024, 9, 1, tzinfo=UTC), availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT
    )
    assert before[sid] is not None and before[sid].value == "105000"  # type: ignore[union-attr]
    assert after[sid] is not None and after[sid].value == "120000"  # type: ignore[union-attr]


def test_as_of_view_before_first_disclosure_returns_none(toyota_histories: dict[str, RevisionHistory]) -> None:
    sid = _toyota_op_forecast_series_id(toyota_histories)
    result = fundamentals_as_of(
        toyota_histories, datetime(2024, 1, 1, tzinfo=UTC), availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT
    )
    assert result[sid] is None  # No Silent Forward Fill: 開示前にForecastは存在しない


# --- Test 11/14: provider_available_atがUNKNOWNの場合、market_public_atへFallbackしない ---


def test_provider_available_at_semantics_defaults_to_none_when_unknown_basis(
    toyota_histories: dict[str, RevisionHistory],
) -> None:
    """Phase4Aではprovider_available_atの実観測ログが無いためavailability_basisは常に
    UNKNOWN。B系統(既定)はUNKNOWN Versionを除外するため、market_public_atが
    分かっていてもFallbackせず、素直にNoneを返す(INSUFFICIENT_DATA相当)。"""
    sid = _toyota_op_forecast_series_id(toyota_histories)
    result = fundamentals_as_of(toyota_histories, datetime(2024, 9, 1, tzinfo=UTC))  # 既定 = PROVIDER_AVAILABLE_AT
    assert result[sid] is None


def test_provider_available_at_semantics_explicit_opt_in_can_use_unknown_basis(
    toyota_histories: dict[str, RevisionHistory],
) -> None:
    sid = _toyota_op_forecast_series_id(toyota_histories)
    result = fundamentals_as_of(toyota_histories, datetime(2024, 9, 1, tzinfo=UTC), include_unknown_availability=True)
    assert result[sid] is not None
    assert result[sid].value == "120000"  # type: ignore[union-attr]


# --- Test 12/13: 未来のDisclosure/Forecast Revisionが過去as_ofへLeakしない ---


def test_future_forecast_revision_does_not_leak_into_past_decision(toyota_histories: dict[str, RevisionHistory]) -> None:
    sid = _toyota_op_forecast_series_id(toyota_histories)
    past_view = fundamentals_as_of(
        toyota_histories, datetime(2024, 6, 1, tzinfo=UTC), availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT
    )
    assert past_view[sid] is not None
    assert past_view[sid].value != "120000"  # type: ignore[union-attr]


# --- Test 14: future Correctionが過去as_ofへLeakしない(is_correction=Trueでも同じ扱い) ---


def test_future_correction_marked_version_does_not_leak_into_past_decision() -> None:
    """Phase4Aは自動でCorrectionを検出しないが、Schema自体はis_correction=Trueの
    Versionも同じavailable_at基準でPIT除外する(Forecast RevisionとCorrectionの
    どちらであっても、未来の情報は過去のDecisionへ流用しない)。"""
    history = RevisionHistory(
        series_id="S1",
        versions=(
            SourceVersion(
                source_record_id="S1",
                source_version_id="v1",
                value="100",
                available_at=datetime(2024, 5, 1, tzinfo=UTC),
                retrieved_at=datetime(2024, 5, 1, tzinfo=UTC),
                availability_basis=AvailabilityBasis.EXACT,
            ),
            SourceVersion(
                source_record_id="S1",
                source_version_id="v2_correction",
                value="90",
                available_at=datetime(2024, 12, 1, tzinfo=UTC),
                retrieved_at=datetime(2024, 12, 1, tzinfo=UTC),
                availability_basis=AvailabilityBasis.EXACT,
                is_correction=True,
                revision_reason="決算数値の訂正",
                supersedes_version_id="v1",
            ),
        ),
    )
    before_correction = history.as_of(datetime(2024, 8, 1, tzinfo=UTC))
    after_correction = history.as_of(datetime(2025, 1, 1, tzinfo=UTC))
    assert before_correction is not None and before_correction.value == "100"
    assert after_correction is not None and after_correction.value == "90"


# --- Property/Invariant Tests ---


def test_invariant_usable_records_available_at_never_exceeds_decision_at(
    toyota_histories: dict[str, RevisionHistory],
) -> None:
    decision_at = datetime(2024, 7, 1, tzinfo=UTC)
    result = fundamentals_as_of(toyota_histories, decision_at, availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT)
    for version in result.values():
        if version is not None:
            assert version.published_at is not None
            assert version.published_at <= decision_at


def test_invariant_earlier_decision_at_never_sees_later_versions(toyota_histories: dict[str, RevisionHistory]) -> None:
    sid = _toyota_op_forecast_series_id(toyota_histories)
    t1 = datetime(2024, 6, 1, tzinfo=UTC)
    t2 = datetime(2024, 9, 1, tzinfo=UTC)
    view_t1 = fundamentals_as_of(toyota_histories, t1, availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT)
    view_t2 = fundamentals_as_of(toyota_histories, t2, availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT)
    assert view_t1[sid] != view_t2[sid]  # type: ignore[comparison-overlap]
    assert view_t1[sid].value == "105000"  # type: ignore[union-attr]


def test_invariant_adding_future_revision_does_not_change_earlier_as_of_view() -> None:
    """Revision追加によって、Revision以前のAs-of Viewが変化しない。"""
    base_versions = (
        SourceVersion(
            source_record_id="S1",
            source_version_id="v1",
            value="100",
            available_at=datetime(2024, 5, 1, tzinfo=UTC),
            retrieved_at=datetime(2024, 5, 1, tzinfo=UTC),
            availability_basis=AvailabilityBasis.EXACT,
        ),
    )
    history_before_revision = RevisionHistory(series_id="S1", versions=base_versions)
    history_with_revision = RevisionHistory(
        series_id="S1",
        versions=(
            *base_versions,
            SourceVersion(
                source_record_id="S1",
                source_version_id="v2",
                value="120",
                available_at=datetime(2024, 8, 1, tzinfo=UTC),
                retrieved_at=datetime(2024, 8, 1, tzinfo=UTC),
                availability_basis=AvailabilityBasis.EXACT,
            ),
        ),
    )
    decision_at = datetime(2024, 6, 1, tzinfo=UTC)
    result_before = history_before_revision.as_of(decision_at)
    result_after = history_with_revision.as_of(decision_at)
    assert result_before is not None and result_after is not None
    assert result_before.value == result_after.value == "100"


def test_as_of_by_semantics_requires_tz_aware_decision_at() -> None:
    history = RevisionHistory(series_id="S1", versions=())
    with pytest.raises(ValueError, match="tz-aware"):
        as_of_by_semantics(history, datetime(2024, 1, 1), availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT)
