"""Phase3A.1で追加したJ-Quants V2変換関数(TOPIX/Corporate Action Event/Universe master data)のテスト。"""

from __future__ import annotations

from datetime import date

import pytest
from lib.data_sources.convert import (
    detect_corporate_action_events_from_equity_bars,
    equities_master_payload_to_listing_records,
    topix_bars_payload_to_raw_bars,
)
from lib.errors import LookAheadBiasError
from lib.market_calendar import JST, session_close_at
from lib.schemas.price_data import (
    CorporateActionType,
    RawOHLCVBar,
    apply_split_adjustments_as_of,
    build_provider_derived_adjusted_bars,
)
from lib.universe import ListingRecord, check_company_name_consistency


def test_topix_bars_payload_to_raw_bars_uses_fixed_topix_code() -> None:
    payload = [{"Date": "2026-01-05", "O": 2500.0, "H": 2510.0, "L": 2490.0, "C": 2505.0}]
    bars = topix_bars_payload_to_raw_bars(payload)
    assert bars[0].code == "TOPIX"
    assert bars[0].close == 2505.0
    assert bars[0].volume is None  # Voフィールドが無い場合はNone(推測しない)


def test_detect_corporate_action_events_ignores_days_with_adj_factor_of_one_and_no_exrt() -> None:
    payload = [
        {"Code": "7203", "Date": "2026-01-05", "AdjFactor": 1.0, "ExRT": None},
        {"Code": "7203", "Date": "2026-01-06", "AdjFactor": 1.0, "ExRT": None},
    ]
    events = detect_corporate_action_events_from_equity_bars(payload)
    assert events == []


def test_detect_corporate_action_events_recognizes_only_the_ex_rights_day() -> None:
    """ユーザー指定の synthetic test: Day1 AdjFactor=1 / Day2 AdjFactor=0.5,ExRT="1" /
    Day3 AdjFactor=1 -> Corporate ActionはDay2の1件だけ認識する(前日比ではなく、
    その日の行自体でCorporate Action Event Dayを判定する。V1時代の前日差分ロジックは
    使わない)。"""
    payload = [
        {"Code": "7203", "Date": "2026-01-05", "AdjFactor": 1.0, "ExRT": None},
        {"Code": "7203", "Date": "2026-01-06", "AdjFactor": 0.5, "ExRT": "1"},
        {"Code": "7203", "Date": "2026-01-07", "AdjFactor": 1.0, "ExRT": None},
    ]
    events = detect_corporate_action_events_from_equity_bars(payload)
    assert len(events) == 1
    event = events[0]
    assert event.code == "7203"
    assert event.effective_date == date(2026, 1, 6)
    assert event.action_type == CorporateActionType.ADJUSTMENT_EVENT
    assert event.announced_at is None
    assert event.raw_adj_factor == 0.5


def test_detect_corporate_action_events_recognizes_ex_rights_day_even_without_adj_factor_change() -> None:
    """ExRTだけが設定されていてもEvent Dayとして認識する(AdjFactor!=1限定ではない)。"""
    payload = [{"Code": "7203", "Date": "2026-01-06", "AdjFactor": 1.0, "ExRT": "2"}]
    events = detect_corporate_action_events_from_equity_bars(payload)
    assert len(events) == 1
    assert events[0].effective_date == date(2026, 1, 6)


def test_detect_corporate_action_events_are_rejected_by_case_a_pit_safe_adjustment() -> None:
    """announced_atが無いV2 Eventは、Case A(Announcementを使う用途)の
    apply_split_adjustments_as_ofに渡すとLookAheadBiasErrorで拒否される
    (意図した挙動、DECISIONS.md D0032)。"""
    payload = [
        {"Code": "7203", "Date": "2026-01-05", "AdjFactor": 1.0, "ExRT": None},
        {"Code": "7203", "Date": "2026-01-06", "AdjFactor": 0.5, "ExRT": "1"},
    ]
    events = detect_corporate_action_events_from_equity_bars(payload)
    with pytest.raises(LookAheadBiasError):
        apply_split_adjustments_as_of([], events, as_of=session_close_at(date(2026, 1, 10)))


def test_build_provider_derived_adjusted_bars_applies_event_once_available() -> None:
    """Case B: Provider由来Eventはannounced_at無しでPrice Series連続化に使える。
    効力発生日のBarデータが取得可能になった時点(session_close_at(effective_date))で
    初めて反映される。"""
    payload = [
        {"Code": "7203", "Date": "2026-01-05", "AdjFactor": 1.0, "ExRT": None},
        {"Code": "7203", "Date": "2026-01-06", "AdjFactor": 0.5, "ExRT": "1"},
    ]
    events = detect_corporate_action_events_from_equity_bars(payload)
    raw_bars = [
        RawOHLCVBar(code="7203", session_date=date(2026, 1, 5), open=2000.0, high=2010.0, low=1990.0, close=2000.0, volume=100),
        RawOHLCVBar(code="7203", session_date=date(2026, 1, 6), open=1000.0, high=1010.0, low=990.0, close=1000.0, volume=200),
    ]
    as_of = session_close_at(date(2026, 1, 6))
    adjusted = build_provider_derived_adjusted_bars(raw_bars, events, as_of=as_of)
    # 2026-01-06のEvent(raw_adj_factor=0.5)は、それより前(2026-01-05)の価格にのみ
    # 乗算される(乗算慣習、未検証。DECISIONS.md D0032参照)。
    by_date = {bar.session_date: bar for bar in adjusted}
    assert by_date[date(2026, 1, 5)].close == pytest.approx(1000.0)  # 2000.0 * 0.5
    assert by_date[date(2026, 1, 6)].close == pytest.approx(1000.0)  # Event当日自身は無調整


def test_build_provider_derived_adjusted_bars_rejects_future_event() -> None:
    """as_of時点でまだ取得可能でないはずのEventが混入していればLookAheadBiasErrorで拒否する。"""
    payload = [{"Code": "7203", "Date": "2026-01-10", "AdjFactor": 0.5, "ExRT": "1"}]
    events = detect_corporate_action_events_from_equity_bars(payload)
    raw_bars = [
        RawOHLCVBar(code="7203", session_date=date(2026, 1, 5), open=2000.0, high=2010.0, low=1990.0, close=2000.0, volume=100),
    ]
    as_of = session_close_at(date(2026, 1, 6))  # Event(1/10)より前の意思決定時点
    with pytest.raises(LookAheadBiasError):
        build_provider_derived_adjusted_bars(raw_bars, events, as_of=as_of)


def test_equities_master_payload_to_listing_records_handles_missing_dates_honestly() -> None:
    """listing_date/delisting_dateに相当するフィールドが無い場合、Noneのまま(推測しない)。"""
    payload = [{"Code": "7203", "CompanyName": "トヨタ自動車", "MarketCode": "0111", "Sector33Code": "3700"}]
    records = equities_master_payload_to_listing_records(payload)
    assert len(records) == 1
    record = records[0]
    assert record.code == "7203"
    assert record.market == "0111"
    assert record.sector == "3700"
    assert record.company_name == "トヨタ自動車"
    assert record.listing_date is None
    assert record.delisting_date is None


def test_equities_master_payload_to_listing_records_uses_dates_when_present() -> None:
    payload = [{"Code": "7203", "MarketCode": "0111", "ListingDate": "1949-05-16", "DelistingDate": ""}]
    records = equities_master_payload_to_listing_records(payload)
    assert records[0].listing_date == date(1949, 5, 16)
    assert records[0].delisting_date is None


def test_check_company_name_consistency_flags_mismatch_against_master() -> None:
    """手入力の会社名がMasterと矛盾する場合に警告を返す(手入力をCanonicalとして扱わない)。"""
    listings = [ListingRecord(code="3626", market="0111", company_name="TIS株式会社")]
    warnings = check_company_name_consistency({"3626": "TOKAIホールディングス"}, listings)
    assert len(warnings) == 1
    assert "3626" in warnings[0]


def test_check_company_name_consistency_passes_when_names_match() -> None:
    listings = [ListingRecord(code="7203", market="0111", company_name="トヨタ自動車")]
    warnings = check_company_name_consistency({"7203": "トヨタ自動車"}, listings)
    assert warnings == []


def test_check_company_name_consistency_flags_unresolvable_code() -> None:
    warnings = check_company_name_consistency({"9999": "存在しない銘柄"}, [])
    assert len(warnings) == 1
    assert "9999" in warnings[0]


# JSTの再エクスポート確認用(このモジュールがmarket_calendarと整合していることを担保)。
def test_jst_is_utc_plus_9() -> None:
    from datetime import timedelta

    assert JST.utcoffset(None) == timedelta(hours=9)
