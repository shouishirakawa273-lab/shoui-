"""銘柄ざっと見スクリーナー(Step 3)。

1銘柄について「いま押さえておくべきこと」を1回の呼び出しで出す。推奨判定・
スコアリング・自動ランキングは行わない。判断は人間がする
(`CLAUDE.md`: 最終的なBUY/HOLD/SELL判断は必ず人間が行う)。

出せるもの:

- 実績財務の年次推移(`financial_trend`)
- 会社予想の改定履歴(`forecast_revisions`)
- 流動性・相関の警告(`lib/pretrade_risk`、Step 1)

出せないもの(推測で埋めない):

- PBR・配当利回り・ROE。`lib/fundamentals/normalize.py` の通り、Share Count関連・
  Dividend関連・`ROE` はRaw Payloadにはあるが Metric へ未マッピングで、Field名を
  推測して読むことは禁止されている
- PER分位。`lib/valuation` にモデルはあるが、駆動するOrchestrationが未整備
  (普通株の割安判断が必要になった時点で着手する)
"""

from __future__ import annotations

from lib.screener.financial_trend import (
    UNMAPPED_METRICS,
    AnnualObservation,
    FinancialTrend,
    MetricTrend,
    build_financial_trend,
)
from lib.screener.forecast_revisions import (
    ForecastRevision,
    ForecastRevisionSeries,
    RevisionDirection,
    build_forecast_revision_series,
    metric_family,
    present_forecast_metrics,
    target_fiscal_year_end,
)
from lib.screener.visibility import visible_versions

__all__ = [
    "UNMAPPED_METRICS",
    "AnnualObservation",
    "FinancialTrend",
    "ForecastRevision",
    "ForecastRevisionSeries",
    "MetricTrend",
    "RevisionDirection",
    "build_financial_trend",
    "build_forecast_revision_series",
    "metric_family",
    "present_forecast_metrics",
    "target_fiscal_year_end",
    "visible_versions",
]
