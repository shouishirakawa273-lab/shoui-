"""保有候補に対する発注前の警告(Step 1)。

D0112 (`lib/portfolio_risk/engine.py`) は `UNSUPPORTED` に `"LIQUIDITY"` と
`"CORRELATION"` を明示的に含める。本パッケージはその2つを独立に補うもので、
D0112の契約・実装には一切触れない。

本パッケージが出すのは警告のための推定値であり、厳密な資本算術でも最適化入力
でもない。VaR、CVaR、ストレス較正、共分散ベースの最適化は引き続き行わない。
"""

from __future__ import annotations

from lib.pretrade_risk.correlation import (
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

__all__ = [
    "CorrelationAssessment",
    "CorrelationOutcome",
    "LiquidityAssessment",
    "LiquidityOutcome",
    "PairCorrelation",
    "assess_correlation",
    "assess_liquidity",
]
