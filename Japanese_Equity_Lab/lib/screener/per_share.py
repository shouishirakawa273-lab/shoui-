"""1株当たり指標の比較可能性(Step 3)。

`financial_trend` が出す実績は**開示時点のまま(as-reported)**であり、株式分割・
併合をさかのぼって調整していない。一方で株価側は
`lib/backtest/price_history.AsOfAdjustedPriceHistory` が調整する。この非対称性を
出力に明示しないと、読み手は分割を業績の急変と読み違える。

2026-11-21の実データ確認(トヨタ7203)では、EPSが

    2021-03-31期 803.23 → 2022-03-31期 205.23

と並び、額面上は74%減に見えた。同じ決算期の `net_profit / eps` を取ると

    2021-03-31期 約27.95億 → 2022-03-31期 約138.87億(4.97倍)

で、1株当たりの基準そのものが切り替わっている。他の年は0.98〜0.99倍(自己株買い
相当の緩やかな減少)であり、この1点だけが不連続である。

本モジュールは**検知して警告するだけ**で、値を補正しない
(ルートCLAUDE.md「異常値は機械的にしか判定できないことを前提にする」)。
不連続の**原因も断定しない**。分割・併合・増資・訂正のいずれでも同じ形になるため、
「per-share基準が不連続」までを事実として述べる。

## 二つの独立した経路

1. **Provider確定のCorporate Action Event**(`CorporateAction.raw_adj_factor`)。
   J-Quants V2のAdjFactorは権利落ち日のrecordに載る公式仕様(D0034)。これは推測を
   含まない一次情報だが、**株価取得Windowの範囲しか見えない**
   (`scripts/screen.py` は600日)。
2. **per-share除数の不連続**(`net_profit / eps`)。追加取得なしで財務推移の全期間を
   覆える。経路1が届かない過去を補う。

経路1が空であることは「イベントが無かった」を意味しない。`known_from` より前は
**UNKNOWN**である(Unknownは0でもfalseでもない)。出力は必ずこの境界を載せる。

## 除数について

`net_profit / eps` は**診断専用の派生量**である。株数として表示しない。他の計算にも
使わない。比の**変化**だけを不連続の signal として使う。実際の発行済株数は
`lib/fundamentals/normalize.py` の通りMetricへ未マッピングであり、ここで代用した
ことにはしない。

## 許容幅

`DEFAULT_DIVISOR_TOLERANCE = 0.25`(±25%)。根拠は銘柄の観測値ではなく一般的性質:

- 分割・併合は定義上、単純な比で基準を変える。日本市場で最小の分割は1:2(2倍)。
- 自己株買い・新株発行による年次の株数変動は通常1桁%にとどまる。

±25%は最小の分割(2倍)まで2倍以上の余裕があり、通常の株数変動からは十分離れている。
**この数値は7203のFY2021→FY2022(4.97倍)を観測した後に設定した**。警告の閾値で
あって戦略パラメータではないためLocked Testを汚染しないが、事前登録ではない
(`RESEARCH_RULES.md` の区別に従い、経緯を記録する)。
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from types import MappingProxyType

from lib.schemas.price_data import CorporateAction
from lib.screener.financial_trend import FinancialTrend, MetricTrend

logger = logging.getLogger(__name__)

PER_SHARE_METRICS: tuple[str, ...] = ("eps", "bps")
"""正規化済みのうち1株当たりの指標。

`bps` は2026-11-24のStep 3 Stage 1でマッピングした。**EPSと同じ不連続を持つ**:
7203のFY行のBPSは 1.154倍 → **0.228倍** → 1.097倍 と並び、FY2022で1株当たりの
基準が切り替わっている。

`distribution_per_unit`(REITの1口当たり分配金)と
`dividend_per_share_annual`(一株当たり配当)も公式に遡及調整されないと明記されて
いるため同じ性質を持つが、**除数にできる総額のMetricが無い**ため本モジュールの
手法では検知できない。ここに入れると「検知できたのに不連続が無い」と誤読される
ので入れない(`unchecked_metrics` でもなく、対象外)。
"""

DIVISOR_SOURCES: dict[str, str] = {
    "eps": "net_profit",
    "bps": "provider_reported_sheq",
}
"""1株当たり指標 -> 除数を作るための総額Metric。

`bps` の除数が自己資本(`ShEq`)で正しいことは**実データで確認した**。7203の
FY2026で `ShEq / BPS = 130.3337億株`、`NP / EPS = 130.3335億株` と6桁一致する
(比 1.000001)。つまりBPSはEPSと同じ1株当たり基準に乗っており、純資産(`Eq`)では
なく自己資本が分子である。推測ではない。

REITでは `ShEq` が空(89510: 0/27)なので `bps` の除数が作れない。その場合は
`unchecked_metrics` に入り、**「不連続なし」とは報告しない**。REITのBPSが何を
分子にしているかは `UNKNOWN` であり、`Eq` で代用すれば推測になる。
"""

DEFAULT_DIVISOR_TOLERANCE = Decimal("0.25")


@dataclass(frozen=True, kw_only=True)
class PerShareBreak:
    """連続する2決算期のあいだで、1株当たりの基準が不連続になった箇所。"""

    metric_type: str
    accounting_standard: str | None
    from_fiscal_period_end: date | None
    to_fiscal_period_end: date | None
    divisor_source_metric: str
    """この不連続を検知するのに使った総額Metric。"""
    divisor_ratio: Decimal
    """後期の除数 / 前期の除数。1.0から離れるほど基準の変化が大きい。"""
    detail: str
    """原因は断定しない。観測した事実のみ。"""


@dataclass(frozen=True, kw_only=True)
class PerShareComparability:
    """1銘柄ぶんの、1株当たり指標の比較可能性。"""

    code: str
    per_share_metrics: tuple[str, ...]
    breaks: tuple[PerShareBreak, ...]
    corporate_action_dates: tuple[date, ...]
    """Provider確定のCorporate Action Eventの権利落ち日。`known_from` 以降のみ。"""
    divisor_sources: tuple[tuple[str, str], ...]
    """実際に使った (1株当たり指標, 除数Metric) の対。"""
    corporate_actions_known_from: date | None
    """Corporate Action Eventを観測できた最も古いセッション。

    これより前にEventが無かったという主張ではない。`None` は株価データが無く、
    経路1が全くUNKNOWNであることを意味する。
    """
    tolerance: Decimal
    unchecked_metrics: tuple[str, ...]
    """除数を取れず不連続判定ができなかった指標。空欄にせず明示する。"""

    @property
    def is_comparable_throughout(self) -> bool:
        """検知した不連続が無い場合のみTrue。

        **「安全」ではない。** `corporate_actions_known_from` より前のEventは
        見えておらず、除数も両指標が揃った期しか取れない。
        """
        return not self.breaks


def _trend_by_period(trend: MetricTrend) -> dict[date, Decimal]:
    out: dict[date, Decimal] = {}
    for obs in trend.observations:
        if obs.fiscal_period_end is not None and obs.value is not None:
            out[obs.fiscal_period_end] = obs.value
    return out


def assess_per_share_comparability(
    *,
    code: str,
    trend: FinancialTrend,
    corporate_actions: Sequence[CorporateAction] = (),
    corporate_actions_known_from: date | None = None,
    per_share_metrics: Sequence[str] = PER_SHARE_METRICS,
    divisor_sources: Mapping[str, str] = MappingProxyType(DIVISOR_SOURCES),
    tolerance: Decimal = DEFAULT_DIVISOR_TOLERANCE,
) -> PerShareComparability:
    """1株当たり指標が全期間を通じて同じ基準かを調べる。

    会計基準が同じseries同士でのみ除数を比較する。基準をまたぐ比較は
    `financial_trend` が既にseriesを分けており、ここで畳み直さない。

    除数は指標ごとに異なる(`DIVISOR_SOURCES`)。除数Metricが `divisor_sources` に
    無い指標、またはその系列が存在しない指標は `unchecked_metrics` に入り、
    **「不連続なし」とは報告しない。**

    値を書き換えないので、戻り値を無視しても推移の数値は変わらない。
    """
    if tolerance <= 0:
        raise ValueError(f"tolerance must be positive: {tolerance!r}")

    breaks: list[PerShareBreak] = []
    unchecked: list[str] = []
    checked_metrics: list[str] = []
    used_sources: list[tuple[str, str]] = []

    for metric_type in per_share_metrics:
        divisor_source_metric = divisor_sources.get(metric_type)
        if divisor_source_metric is None:
            # 除数の作り方が決まっていない指標。黙って「問題なし」にしない。
            unchecked.append(metric_type)
            continue

        targets = [t for t in trend.trends if t.metric_type == metric_type]
        if not targets:
            unchecked.append(metric_type)
            continue
        checked_metrics.append(metric_type)
        used_sources.append((metric_type, divisor_source_metric))

        divisor_trends = {t.accounting_standard: t for t in trend.trends if t.metric_type == divisor_source_metric}

        checked_any = False
        for target in targets:
            source = divisor_trends.get(target.accounting_standard)
            if source is None:
                continue

            per_share = _trend_by_period(target)
            totals = _trend_by_period(source)
            divisors: dict[date, Decimal] = {}
            for period, value in per_share.items():
                total = totals.get(period)
                if total is None or value == 0:
                    continue
                divisors[period] = total / value

            periods = sorted(divisors)
            if len(periods) >= 2:
                checked_any = True
            for earlier, later in zip(periods, periods[1:], strict=False):
                before = divisors[earlier]
                after = divisors[later]
                if before == 0:
                    continue
                ratio = after / before
                if abs(ratio - 1) <= tolerance:
                    continue
                breaks.append(
                    PerShareBreak(
                        metric_type=metric_type,
                        accounting_standard=target.accounting_standard,
                        from_fiscal_period_end=earlier,
                        to_fiscal_period_end=later,
                        divisor_source_metric=divisor_source_metric,
                        divisor_ratio=ratio,
                        detail=(
                            f"{divisor_source_metric}/{metric_type} が {earlier.isoformat()} 期から "
                            f"{later.isoformat()} 期で約{ratio:.2f}倍に変化した。"
                            f"この境界をまたぐ {metric_type} は同じ1株当たり基準ではない"
                            "(原因は分割・併合・増資・訂正のいずれとも断定しない)。"
                        ),
                    )
                )

        if not checked_any and metric_type not in unchecked:
            unchecked.append(metric_type)

    action_dates = tuple(
        sorted({a.effective_date for a in corporate_actions if a.code == code and a.raw_adj_factor not in (None, 1.0)})
    )

    if breaks:
        logger.info(
            "screener: %s has %d per-share basis discontinuity(ies); values are reported as-is, not adjusted",
            code,
            len(breaks),
        )

    return PerShareComparability(
        code=code,
        per_share_metrics=tuple(checked_metrics),
        breaks=tuple(breaks),
        corporate_action_dates=action_dates,
        corporate_actions_known_from=corporate_actions_known_from,
        divisor_sources=tuple(used_sources),
        tolerance=tolerance,
        unchecked_metrics=tuple(unchecked),
    )
