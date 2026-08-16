from __future__ import annotations

from lib.schemas.portfolio_rules import PortfolioRules
from lib.schemas.strategy import RetirementCriterion, Strategy, StrategyStatus


def test_strategy_defaults_to_watch() -> None:
    strategy = Strategy(
        strategy_id="S0001",
        hypothesis_id="H0001",
        name="earnings_revision_underreaction",
        description="上方修正後の株価反応の遅れを取る戦略",
    )
    assert strategy.status == StrategyStatus.WATCH
    assert strategy.retirement_criteria == ()


def test_strategy_with_retirement_criteria() -> None:
    criterion = RetirementCriterion(
        description="直近12か月Alphaがマイナス",
        metric="rolling_12m_alpha",
        threshold=0.0,
        comparator="<",
    )
    strategy = Strategy(
        strategy_id="S0001",
        hypothesis_id="H0001",
        name="earnings_revision_underreaction",
        description="上方修正後の株価反応の遅れを取る戦略",
        status=StrategyStatus.ACTIVE,
        retirement_criteria=(criterion,),
    )
    assert strategy.retirement_criteria[0].metric == "rolling_12m_alpha"


def test_portfolio_rules_are_separate_from_signal_definition() -> None:
    rules = PortfolioRules(
        rules_id="PR0001",
        max_position_weight=0.05,
        max_sector_weight=0.20,
        max_theme_weight=0.30,
        minimum_cash=0.05,
        earnings_event_exposure="決算発表前後3営業日はポジションを持たない",
        liquidity_constraint="1日平均売買代金の1%以内",
    )
    assert rules.max_position_weight == 0.05
