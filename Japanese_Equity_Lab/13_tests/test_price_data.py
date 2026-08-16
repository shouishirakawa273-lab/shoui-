from __future__ import annotations

from datetime import date

from lib.schemas.price_data import (
    CorporateAction,
    CorporateActionType,
    RawOHLCVBar,
    apply_split_adjustments,
)


def test_split_adjustment_scales_pre_split_prices_down() -> None:
    raw_bars = [
        RawOHLCVBar(code="7203", session_date=date(2026, 1, 5), open=2000, high=2010, low=1990, close=2000, volume=1000),
        RawOHLCVBar(code="7203", session_date=date(2026, 2, 5), open=1010, high=1020, low=1000, close=1010, volume=2000),
    ]
    split = CorporateAction(
        code="7203",
        action_type=CorporateActionType.SPLIT,
        effective_date=date(2026, 2, 1),
        split_ratio=2.0,
    )
    adjusted = apply_split_adjustments(raw_bars, [split])

    before_split = next(b for b in adjusted if b.session_date == date(2026, 1, 5))
    after_split = next(b for b in adjusted if b.session_date == date(2026, 2, 5))

    assert before_split.close == 1000  # 2000 / 2.0
    assert before_split.volume == 2000  # 1000 * 2.0
    assert after_split.close == 1010  # 分割後は無調整
    assert after_split.split_adjustment_factor == 1.0


def test_split_adjustment_handles_missing_prices() -> None:
    raw_bars = [
        RawOHLCVBar(code="7203", session_date=date(2026, 1, 5), open=None, high=None, low=None, close=None, volume=None),
    ]
    adjusted = apply_split_adjustments(raw_bars, [])
    assert adjusted[0].close is None
