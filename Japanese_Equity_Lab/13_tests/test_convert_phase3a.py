"""Phase3Aで追加した変換関数(TOPIX/Corporate Action hint/Universe master data)のテスト。"""

from __future__ import annotations

from datetime import date

import pytest
from lib.data_sources.convert import (
    detect_split_hints_from_daily_quotes,
    index_prices_payload_to_raw_bars,
    listed_info_payload_to_listing_records,
)
from lib.errors import LookAheadBiasError
from lib.market_calendar import JST
from lib.schemas.price_data import CorporateActionType, apply_split_adjustments_as_of


def test_index_prices_payload_to_raw_bars_uses_explicit_code() -> None:
    payload = [{"Date": "2026-01-05", "Open": 2500.0, "High": 2510.0, "Low": 2490.0, "Close": 2505.0}]
    bars = index_prices_payload_to_raw_bars(payload, code="0000")
    assert bars[0].code == "0000"
    assert bars[0].close == 2505.0
    assert bars[0].volume is None  # Volumeフィールドが無い場合はNone(推測しない)


def test_detect_split_hints_ignores_adjustment_factor_of_one() -> None:
    payload = [
        {"Code": "7203", "Date": "2026-01-05", "AdjustmentFactor": 1.0},
        {"Code": "7203", "Date": "2026-01-06", "AdjustmentFactor": 1.0},
    ]
    hints = detect_split_hints_from_daily_quotes(payload)
    assert hints == []


def test_detect_split_hints_extracts_candidate_with_announced_at_none() -> None:
    payload = [
        {"Code": "7203", "Date": "2026-01-05", "AdjustmentFactor": 1.0},
        {"Code": "7203", "Date": "2026-01-06", "AdjustmentFactor": 2.0},  # 分割候補
    ]
    hints = detect_split_hints_from_daily_quotes(payload)
    assert len(hints) == 1
    hint = hints[0]
    assert hint.code == "7203"
    assert hint.effective_date == date(2026, 1, 6)
    assert hint.action_type == CorporateActionType.SPLIT
    assert hint.announced_at is None
    assert "Point-in-Time安全性を検証できない" in (hint.note or "")


def test_detect_split_hints_are_rejected_by_pit_safe_adjustment() -> None:
    """announced_atが無いhintは、既存のPIT-safe変換(apply_split_adjustments_as_of)へ
    渡すとLookAheadBiasErrorで拒否される(意図した挙動、DECISIONS.md D0025)。"""
    payload = [
        {"Code": "7203", "Date": "2026-01-05", "AdjustmentFactor": 1.0},
        {"Code": "7203", "Date": "2026-01-06", "AdjustmentFactor": 2.0},
    ]
    hints = detect_split_hints_from_daily_quotes(payload)
    from lib.market_calendar import session_close_at

    with pytest.raises(LookAheadBiasError):
        apply_split_adjustments_as_of([], hints, as_of=session_close_at(date(2026, 1, 10)))


def test_detect_split_hints_deduplicates_when_factor_stays_elevated_across_many_days() -> None:
    """AdjustmentFactorが分割後も複数日にわたって同じ値を保持し続ける場合(実際のJ-Quantsの
    付与方式として想定されるconventionの1つ)、変化した初日だけを候補として抽出し、
    値を保持している後続日を重複して抽出しない(D0025で修正したバグの回帰テスト)。"""
    payload = [{"Code": "7203", "Date": "2026-01-05", "AdjustmentFactor": 1.0}]
    payload += [{"Code": "7203", "Date": f"2026-01-{day:02d}", "AdjustmentFactor": 2.0} for day in range(6, 26)]
    hints = detect_split_hints_from_daily_quotes(payload)
    assert len(hints) == 1
    assert hints[0].effective_date == date(2026, 1, 6)


def test_listed_info_payload_to_listing_records_handles_missing_dates_honestly() -> None:
    """listing_date/delisting_dateに相当するフィールドが無い場合、Noneのまま(推測しない)。"""
    payload = [{"Code": "7203", "CompanyName": "Toyota", "MarketCode": "0111", "Sector33Code": "3700"}]
    records = listed_info_payload_to_listing_records(payload)
    assert len(records) == 1
    record = records[0]
    assert record.code == "7203"
    assert record.market == "0111"
    assert record.sector == "3700"
    assert record.listing_date is None
    assert record.delisting_date is None


def test_listed_info_payload_to_listing_records_uses_dates_when_present() -> None:
    payload = [{"Code": "7203", "MarketCode": "0111", "ListingDate": "1949-05-16", "DelistingDate": ""}]
    records = listed_info_payload_to_listing_records(payload)
    assert records[0].listing_date == date(1949, 5, 16)
    assert records[0].delisting_date is None


# JSTの再エクスポート確認用(このモジュールがmarket_calendarと整合していることを担保)。
def test_jst_is_utc_plus_9() -> None:
    from datetime import timedelta

    assert JST.utcoffset(None) == timedelta(hours=9)
