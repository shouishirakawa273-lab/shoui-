"""保有候補に対する発注前の警告(Step 1)。

D0112 (`lib/portfolio_risk/engine.py`) は `UNSUPPORTED` に `"LIQUIDITY"` と
`"CORRELATION"` を明示的に含める。本パッケージはその2つを独立に補うもので、
D0112の契約・実装には一切触れない。

本パッケージが出すのは警告のための推定値であり、厳密な資本算術でも最適化入力
でもない。VaR、CVaR、ストレス較正、共分散ベースの最適化は引き続き行わない。

PIT境界は `window.py` に集約してある。`PriceHistorySource` への依存だけでは
日付粒度の保証しか得られないため、大引け未到来セッションの除外、重複セッションの
排除、古さの計測をそこで行う。
"""

from __future__ import annotations

from lib.pretrade_risk.correlation import (
    CodeCoverage,
    CorrelationAssessment,
    CorrelationOutcome,
    PairCorrelation,
    assess_correlation,
)
from lib.pretrade_risk.liquidity import (
    LiquidityAssessment,
    LiquidityOutcome,
    assess_liquidity,
)
from lib.pretrade_risk.window import BarWindow, available_bars, require_aware

__all__ = [
    "BarWindow",
    "CodeCoverage",
    "CorrelationAssessment",
    "CorrelationOutcome",
    "LiquidityAssessment",
    "LiquidityOutcome",
    "PairCorrelation",
    "assess_correlation",
    "assess_liquidity",
    "available_bars",
    "require_aware",
]
