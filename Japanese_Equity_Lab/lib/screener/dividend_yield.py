"""配当利回り(現在値のみ)。

方針書 Step 3 の出力項目のうち、**どのEndpointにも存在しない唯一の指標**。
`/equities/valuation` の11項目にも含まれないので、出すなら必ず導出になる
(`JQUANTS_V2_STEP3_SOURCE_ONBOARDING.md` §10)。

## 現在値だけにする理由

一株当たり配当は**開示時点のままで株式分割の遡及調整がされない**(公式明記)。
`lib/screener/per_share.py` がEPS・BPSで検知している不連続と同じ性質である。

ただし**現在値は安全**である。最新のDPSと最新の株価は同じ基準に乗っており、
期をまたぐ比較が起きないため、分割の段差を踏まない。**10年分位は踏む。**
だから分位は出さない(オーナー判断、2026-11-22)。

## 予想と実績を両方出し、どちらかを黙って選ばない

市場慣行の「配当利回り」は**予想**配当ベースだが、実績ベースも成り立つ。
片方が無いときにもう片方へ暗黙に落とすと、**同じ名前で別の量を出すことになる。**
そこで両方を基準ラベル付きで並べ、無いものは無いと言う。

## 銘柄種別でFieldを決め打ちする

- 株式 → `dividend_per_share_annual`(一株当たり配当)
- REIT → `distribution_per_unit`(1口当たり分配金)

**nullを見てから切り替えない。** 理由は `lib/screener/instrument.py` のとおり。
REITで `dividend_per_share_annual` が空(89510: 0/27)なのは取得失敗ではなく、
REITがその概念で開示していないためである。逆も同じ(7203: `DivUnit` 0/41)。

`InstrumentKind.OTHER`(ETF・優先出資証券)と `UNKNOWN` では、どのFieldが適切か
確認していないので**何も出さない**。推測で読まない。
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from lib.screener.financial_trend import FinancialTrend
from lib.screener.forecast_revisions import ForecastRevisionSeries, metric_family
from lib.screener.instrument import InstrumentKind

logger = logging.getLogger(__name__)


class DividendBasis(StrEnum):
    """利回りの分子が何か。**同じ指標の2つの測定値ではなく、別の量である。**"""

    FORECAST = "FORECAST"
    """当期の会社予想配当。市場慣行の「配当利回り」はこちら。"""
    TRAILING = "TRAILING"
    """直近に確定した期の実績配当。"""


_ACTUAL_METRIC_BY_KIND: dict[InstrumentKind, str] = {
    InstrumentKind.SHARE: "dividend_per_share_annual",
    InstrumentKind.REIT: "distribution_per_unit",
}


@dataclass(frozen=True, kw_only=True)
class DividendYieldFigure:
    basis: DividendBasis
    source_metric_type: str
    """どのMetricから取った値か。基準を追えるようにする。"""
    dividend: Decimal
    yield_ratio: Decimal
    """配当 ÷ 株価。**小数**(0.0312 = 3.12%)。パーセントにしない。"""
    fiscal_period_end: date | None
    published_at: datetime | None


@dataclass(frozen=True, kw_only=True)
class DividendYieldAssessment:
    code: str
    instrument_kind: InstrumentKind
    price: Decimal | None
    price_session: date | None
    figures: tuple[DividendYieldFigure, ...]
    unknown_reason: str | None
    """何も出せなかった理由。空欄にせず明示する(ルートCLAUDE.md)。"""

    @property
    def forecast(self) -> DividendYieldFigure | None:
        return next((f for f in self.figures if f.basis is DividendBasis.FORECAST), None)

    @property
    def trailing(self) -> DividendYieldFigure | None:
        return next((f for f in self.figures if f.basis is DividendBasis.TRAILING), None)


def _latest_actual(trend: FinancialTrend, metric_type: str) -> tuple[Decimal, date | None, datetime | None] | None:
    """実績配当の、最も新しい決算期の観測。

    `build_financial_trend` が既にPITで絞り、Versionも最新を採っている。
    同じ指標が会計基準ごとに複数seriesへ分かれるので、**決算期が最も新しいもの**を
    採る(基準をまたいで値を合成しない。1点を選ぶだけ)。
    """
    best: tuple[Decimal, date | None, datetime | None] | None = None
    best_key: date | None = None
    for series in trend.trends:
        if series.metric_type != metric_type:
            continue
        for obs in series.observations:
            if obs.value is None or obs.fiscal_period_end is None:
                continue
            if best_key is None or obs.fiscal_period_end > best_key:
                best_key = obs.fiscal_period_end
                best = (obs.value, obs.fiscal_period_end, obs.published_at)
    return best


def _current_forecast(
    forecast_series: Sequence[ForecastRevisionSeries],
    family: str,
    *,
    decision_at: datetime,
) -> tuple[Decimal, date | None, datetime | None] | None:
    """当期の会社予想配当。

    対象決算期が判定時点以降で最も近いseriesを選び、その中で**数値が入っている
    最後の改定**を採る。年度確定で枠が空になった後も、最後の有効値が残る。
    """
    as_of = decision_at.date()
    candidates = [
        s
        for s in forecast_series
        if s.metric_family == family and s.target_fiscal_year_end is not None and s.target_fiscal_year_end >= as_of
    ]
    if not candidates:
        return None
    series = min(candidates, key=lambda s: s.target_fiscal_year_end or date.max)
    for revision in reversed(series.revisions):
        if revision.value is not None:
            return (revision.value, series.target_fiscal_year_end, revision.published_at)
    return None


def _to_decimal_price(price: Decimal | float | None) -> Decimal | None:
    """株価をDecimalにする。**`str()` を経由することが必須。**

    株価パイプラインは意図的にfloatである(`lib/pretrade_risk/liquidity.py`:
    「判定ではなくスクリーニングなのでDecimalの厳密contextではなくfloatを用いる」)。
    一方、配当は開示文字列由来なのでDecimalで保持している。利回りは両者をまたぐ。

    `Decimal(0.1)` は `Decimal('0.1000000000000000055511151231257827...')` になる。
    `Decimal(str(0.1))` は `Decimal('0.1')`。**後者でなければ、2進浮動小数の展開を
    そのまま利回りに持ち込む。** 「簡潔にする」つもりで `str()` を外さないこと。
    """
    if price is None:
        return None
    if isinstance(price, Decimal):
        return price
    return Decimal(str(price))


def assess_dividend_yield(
    *,
    code: str,
    instrument_kind: InstrumentKind,
    price: Decimal | float | None,
    price_session: date | None,
    actual_trend: FinancialTrend,
    forecast_series: Sequence[ForecastRevisionSeries] = (),
    decision_at: datetime,
) -> DividendYieldAssessment:
    """配当利回りの現在値を、基準ラベル付きで出す。

    株価が無い、配当が無い、銘柄種別が対象外——いずれも `figures` を空にして
    `unknown_reason` を埋める。**0や空欄にしない。**
    """

    resolved_price = _to_decimal_price(price)

    def _empty(reason: str) -> DividendYieldAssessment:
        return DividendYieldAssessment(
            code=code,
            instrument_kind=instrument_kind,
            price=resolved_price,
            price_session=price_session,
            figures=(),
            unknown_reason=reason,
        )

    metric_type = _ACTUAL_METRIC_BY_KIND.get(instrument_kind)
    if metric_type is None:
        return _empty(f"InstrumentKind={instrument_kind.value} ではどの配当Fieldが適切か確認していないため算出しない")
    if resolved_price is None:
        return _empty("株価が取得できないため算出できない")
    if resolved_price <= 0:
        return _empty(f"株価が正の値でないため算出できない(price={resolved_price})")

    family = metric_family(metric_type)
    figures: list[DividendYieldFigure] = []

    forecast = _current_forecast(forecast_series, family, decision_at=decision_at)
    if forecast is not None:
        value, period_end, published_at = forecast
        figures.append(
            DividendYieldFigure(
                basis=DividendBasis.FORECAST,
                source_metric_type=f"{family}_current_year_forecast",
                dividend=value,
                yield_ratio=value / resolved_price,
                fiscal_period_end=period_end,
                published_at=published_at,
            )
        )

    trailing = _latest_actual(actual_trend, metric_type)
    if trailing is not None:
        value, period_end, published_at = trailing
        figures.append(
            DividendYieldFigure(
                basis=DividendBasis.TRAILING,
                source_metric_type=metric_type,
                dividend=value,
                yield_ratio=value / resolved_price,
                fiscal_period_end=period_end,
                published_at=published_at,
            )
        )

    if not figures:
        return _empty(f"{metric_type} の予想・実績いずれも判定時点で可視でない")

    logger.info("screener: %s dividend yield from %d basis/bases", code, len(figures))
    return DividendYieldAssessment(
        code=code,
        instrument_kind=instrument_kind,
        price=resolved_price,
        price_session=price_session,
        figures=tuple(figures),
        unknown_reason=None,
    )
