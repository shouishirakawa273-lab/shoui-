from __future__ import annotations

from datetime import date, datetime

import pytest
from lib.errors import LookAheadBiasError
from lib.market_calendar import JST, session_close_at
from lib.schemas.price_data import (
    CorporateAction,
    CorporateActionType,
    RawOHLCVBar,
    apply_split_adjustments,
    apply_split_adjustments_as_of,
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


def test_apply_split_adjustments_as_of_rejects_not_yet_announced_split() -> None:
    """decision_atより後に公表される分割を渡すこと自体が未来情報の混入として拒否される。"""
    raw_bars = [
        RawOHLCVBar(code="7203", session_date=date(2026, 1, 5), open=2000, high=2010, low=1990, close=2000, volume=1000),
    ]
    split_announced_later = CorporateAction(
        code="7203",
        action_type=CorporateActionType.SPLIT,
        effective_date=date(2026, 2, 1),
        announced_at=datetime(2026, 1, 20, 16, 0, tzinfo=JST),  # decision_atより後に公表
        split_ratio=2.0,
    )
    decision_at = session_close_at(date(2026, 1, 10))

    with pytest.raises(LookAheadBiasError):
        apply_split_adjustments_as_of(raw_bars, [split_announced_later], as_of=decision_at)


def test_apply_split_adjustments_as_of_does_not_adjust_before_effective_date() -> None:
    """known_at(announced_at)を過ぎていても、adjustable_at(effective_date)を過ぎるまでは調整しない。

    ユーザー提示のシナリオ: 8/1分割発表、8/15が意思決定時点、10/1が分割の効力発生日。
    8/15時点では「将来分割される」ことは分かるが、10/1の分割比率で8/15時点の過去
    Price Featureを未来基準へ補正してはならない。
    """
    raw_bars = [
        RawOHLCVBar(code="7203", session_date=date(2026, 7, 1), open=2000, high=2010, low=1990, close=2000, volume=1000),
    ]
    split_announced_but_not_yet_effective = CorporateAction(
        code="7203",
        action_type=CorporateActionType.SPLIT,
        effective_date=date(2026, 10, 1),
        announced_at=datetime(2026, 8, 1, 9, 0, tzinfo=JST),
        split_ratio=2.0,
    )
    decision_at = session_close_at(date(2026, 8, 15))

    adjusted = apply_split_adjustments_as_of(raw_bars, [split_announced_but_not_yet_effective], as_of=decision_at)

    assert adjusted[0].close == 2000  # 発表済みだがまだ効力発生前なので無調整
    assert adjusted[0].split_adjustment_factor == 1.0


def test_apply_split_adjustments_as_of_adjusts_once_effective_date_has_passed() -> None:
    """同じCorporate Actionでも、decision_atがeffective_dateを過ぎていれば調整が反映される。"""
    raw_bars = [
        RawOHLCVBar(code="7203", session_date=date(2026, 7, 1), open=2000, high=2010, low=1990, close=2000, volume=1000),
    ]
    split = CorporateAction(
        code="7203",
        action_type=CorporateActionType.SPLIT,
        effective_date=date(2026, 10, 1),
        announced_at=datetime(2026, 8, 1, 9, 0, tzinfo=JST),
        split_ratio=2.0,
    )
    decision_at = session_close_at(date(2026, 10, 15))  # effective_date(10/1)より後

    adjusted = apply_split_adjustments_as_of(raw_bars, [split], as_of=decision_at)

    assert adjusted[0].close == 1000  # 効力発生済みなので調整される


def test_apply_split_adjustments_as_of_rejects_unresolved_announced_at() -> None:
    raw_bars = [
        RawOHLCVBar(code="7203", session_date=date(2026, 1, 5), open=2000, high=2010, low=1990, close=2000, volume=1000),
    ]
    action_without_announced_at = CorporateAction(
        code="7203",
        action_type=CorporateActionType.SPLIT,
        effective_date=date(2026, 2, 1),
        split_ratio=2.0,
    )
    with pytest.raises(LookAheadBiasError):
        apply_split_adjustments_as_of(raw_bars, [action_without_announced_at], as_of=session_close_at(date(2026, 1, 10)))
