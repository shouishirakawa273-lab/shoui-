from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

import pytest
from lib.schemas.paper_trade import PaperTrade, Signal


def _trade(**overrides: object) -> PaperTrade:
    defaults: dict[str, object] = dict(
        paper_trade_id="PT0001",
        hypothesis_id="H0001",
        strategy_id="S0001",
        timestamp=datetime(2026, 8, 17, 9, 0, tzinfo=UTC),
        ticker="7203",
        price=2000.0,
        signal=Signal.BUY,
        expected_return=0.05,
        expected_excess_return=0.02,
        probability=0.6,
        confidence="MEDIUM",
        reason="上方修正発表",
        counter_argument="すでに株価に織り込み済みの可能性",
        invalidation_condition="次の決算で下方修正が出た場合",
    )
    defaults.update(overrides)
    return PaperTrade(**defaults)  # type: ignore[arg-type]


def test_paper_trade_defaults_to_shadow_portfolio() -> None:
    trade = _trade()
    assert trade.selected_by_human is False


def test_paper_trade_reason_cannot_be_rewritten() -> None:
    """理由は後から書き換えない: frozenなのでdataclasses.replace以外での変更は型的に禁止される。"""
    trade = _trade()
    with pytest.raises(dataclasses.FrozenInstanceError):
        trade.reason = "書き換えテスト"  # type: ignore[misc]
