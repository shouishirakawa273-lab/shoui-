"""Phase4A(D0043 追記): 7203(トヨタ自動車)Local Real Data Validationで確認した
実DiscDateを用いたPIT Regression Test。

2026-08-16のLocal Real Data Validationで、7203の実Disclosureとして以下の
DiscDateがユーザーから報告された:

    2024-02-06 / 2024-05-08 / 2024-08-01 / 2024-11-06

**このTestの限界(重要)**: DiscTime(時刻)・実際の財務数値はこのセッションでは
報告されていない。以下のTestはPIT境界判定ロジック(as_ofが週〜月単位disclosure
dateから離れている場合の可用性判定)のみを検証するものであり、`_PLACEHOLDER_HOUR`
(15:00 JST)や`PLACEHOLDER`という値そのものを実際に確認されたFactとして主張する
ものではない。実運用でこれらのPlaceholderをFactとして扱わないこと。
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from lib.evidence.model import AvailabilityBasis, AvailabilitySemantics, RevisionHistory, SourceVersion
from lib.fundamentals.view import fundamentals_as_of

_JST = ZoneInfo("Asia/Tokyo")
_PLACEHOLDER_HOUR = 15  # DiscTime未確認のためTest専用Placeholder(Docstring参照)
_REAL_DISC_DATES = ("2024-02-06", "2024-05-08", "2024-08-01", "2024-11-06")


def _published_at(disc_date: str) -> datetime:
    year, month, day = (int(part) for part in disc_date.split("-"))
    return datetime(year, month, day, _PLACEHOLDER_HOUR, 0, tzinfo=_JST)


def _real_dates_history(*, availability_basis: AvailabilityBasis) -> RevisionHistory:
    series_id = "7203_LOCAL_REAL_DATA_VALIDATION_PLACEHOLDER_SERIES"
    versions = tuple(
        SourceVersion(
            source_record_id=series_id,
            source_version_id=f"v{i}",
            value="PLACEHOLDER",  # 実数値はこのメッセージでは未報告
            available_at=_published_at(disc_date),
            retrieved_at=_published_at(disc_date),
            availability_basis=availability_basis,
            published_at=_published_at(disc_date),
        )
        for i, disc_date in enumerate(_REAL_DISC_DATES)
    )
    return RevisionHistory(series_id=series_id, versions=versions)


# --- Market Information Study(A系統)、実Disclosure Dateでの境界確認 ---


def test_real_dates_as_of_2024_03_01_sees_feb06_not_may08() -> None:
    history = _real_dates_history(availability_basis=AvailabilityBasis.EXACT)
    result = fundamentals_as_of(
        {history.series_id: history},
        datetime(2024, 3, 1, tzinfo=UTC),
        availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT,
    )
    version = result[history.series_id]
    assert version is not None
    assert version.published_at == _published_at("2024-02-06")
    assert version.published_at != _published_at("2024-05-08")


def test_real_dates_as_of_2024_09_01_sees_aug01_not_nov06() -> None:
    history = _real_dates_history(availability_basis=AvailabilityBasis.EXACT)
    result = fundamentals_as_of(
        {history.series_id: history},
        datetime(2024, 9, 1, tzinfo=UTC),
        availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT,
    )
    version = result[history.series_id]
    assert version is not None
    assert version.published_at == _published_at("2024-08-01")
    assert version.published_at != _published_at("2024-11-06")


def test_real_dates_as_of_before_first_disclosure_returns_none() -> None:
    history = _real_dates_history(availability_basis=AvailabilityBasis.EXACT)
    result = fundamentals_as_of(
        {history.series_id: history},
        datetime(2024, 1, 1, tzinfo=UTC),
        availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT,
    )
    assert result[history.series_id] is None


# --- Reproducible System Simulation(B系統): provider_available_at UNKNOWNはFallbackしない ---


def test_real_dates_provider_available_at_unknown_does_not_fallback_to_market_public_at() -> None:
    """このLabではprovider_available_atの実観測ログが無いため、Local Real Data
    Validationで確認した実Disclosure Dateに対しても、B系統(既定)は
    market_public_atへFallbackせず`None`を返す既存原則を維持する(D0043)。"""
    history = _real_dates_history(availability_basis=AvailabilityBasis.UNKNOWN)
    result = fundamentals_as_of({history.series_id: history}, datetime(2024, 9, 1, tzinfo=UTC))  # 既定 = PROVIDER_AVAILABLE_AT
    assert result[history.series_id] is None


def test_real_dates_provider_available_at_explicit_opt_in_matches_market_public_at_when_basis_exact() -> None:
    history = _real_dates_history(availability_basis=AvailabilityBasis.EXACT)
    result = fundamentals_as_of(
        {history.series_id: history},
        datetime(2024, 9, 1, tzinfo=UTC),
        include_unknown_availability=True,
    )
    version = result[history.series_id]
    assert version is not None
    assert version.published_at == _published_at("2024-08-01")
