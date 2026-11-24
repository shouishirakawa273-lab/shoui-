"""スクリーナーの1画面表示(Step 3)。

方針書 Step 3 の受入基準は「銘柄コード1つで上記が**1画面または1CSV**で出る」。
JSONは3銘柄で409KB・5690行あり(2026-11-24実測)、機械は読めても人は読まない。
「使われないツールは完成していない」と方針書が書いている以上、読むのに苦労する形
しか無い状態は受入基準を満たしていない。本モジュールはその1画面を作る。

## 入れないもの

**推奨判定・スコアリング・自動ランキングを入れない**(方針書「やらないこと」)。
「割安」「買い」のような語を出さない。数字と警告を並べ、読むのは人間である。

分位も「41%」と出すだけで、低い/高いの評価語を付けない。

## 取得不可は空欄にしない

ルート `CLAUDE.md` のとおり、取得できない値は空白ではなく理由とともに示す。
1画面に収めるため理由は短縮するが、**消さない**。詳細はJSONにある。

## 予想値にはラベルと出典日を付ける

同じくルール1。予想は「予想」と明示し、どの決算期に対するものかを併記する。
"""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal

from lib.pretrade_risk.correlation import CorrelationAssessment, CorrelationOutcome
from lib.pretrade_risk.liquidity import LiquidityAssessment, LiquidityOutcome
from lib.screener.dividend_yield import DividendBasis, DividendYieldAssessment
from lib.screener.earnings_schedule import EarningsSchedule
from lib.screener.financial_trend import FinancialTrend
from lib.screener.forecast_revisions import ForecastRevisionSeries
from lib.screener.instrument import InstrumentKind
from lib.screener.per_share import PerShareComparability
from lib.screener.valuation_percentile import ValuationPercentiles

_ROE_METRIC = "provider_reported_roe"
_UNAVAILABLE = "取得不可"
_FORECAST_FAMILY_PRIORITY: tuple[str, ...] = (
    "operating_profit",
    "eps",
    "net_profit",
    "sales",
    "dividend_per_share_annual",
    "ordinary_profit",
    "distribution_per_unit",
)
"""予想改定を表示する順序。**優劣の判断ではなく表示順**である。

2026-11-24、`eps` 固定で表示していたため、6758と8951で「取得不可」と出していた。
実際にはどちらも予想を開示しており、1株当たりEPSだけが空だった(6758は営業利益・
売上・純利益・配当に値があり、8951は営業利益・経常利益・売上に値がある)。
**あるデータを無いと表示していた。**

営業利益を先頭にしたのは、日本の決算短信で会社予想の中心に置かれるのがそれで
あるため。EPSが次。どれが重要かの判定はしない——値のあるものを順に出すだけ。
"""

_MAX_FORECAST_FAMILIES = 2
"""1画面に収めるための表示上限。残りはJSONにある。"""

_FAMILY_LABELS: dict[str, str] = {
    "operating_profit": "営業利益",
    "ordinary_profit": "経常利益",
    "net_profit": "純利益",
    "sales": "売上",
    "eps": "EPS",
    "dividend_per_share_annual": "配当",
    "distribution_per_unit": "分配金",
}
"""表示用の短縮名。**JSONには内部のmetric_type名がそのまま入る**(突き合わせ用)。

`operating_profit` は18セルあり、ラベル列(14セル)を超えて値と衝突していた。
"""

_PER_SHARE_FAMILIES = frozenset({"eps", "dividend_per_share_annual", "distribution_per_unit"})
"""1株(1口)当たりの指標。円単位に丸めず、そのまま出す。"""

_MAX_HISTORY_POINTS = 10
"""推移に並べる最大期数。

REITは半期開示なので10年で20点になり(89510で実測)、1行に並べると読めない。
**間引かず末尾から切り、何期中の何期かを明示する。**
"""


def _yen(value: Decimal) -> str:
    """金額を兆・億で丸める。13桁の数字列は1画面の目的を損ねる。

    2026-11-24、営業利益予想が `3000000000000.00` と出ていた(3兆円)。
    """
    amount = float(value)
    sign = "-" if amount < 0 else ""
    magnitude = abs(amount)
    if magnitude >= 1e12:
        return f"{sign}{magnitude / 1e12:.2f}兆"
    if magnitude >= 1e8:
        return f"{sign}{magnitude / 1e8:.0f}億"
    return f"{sign}{magnitude:,.0f}"


_LABEL_WIDTH = 14
"""ラベル列の表示幅(セル数)。文字数ではない——下記 `_display_width` 参照。"""


def _display_width(text: str) -> int:
    """等幅端末での表示幅。全角は2セルを占める。

    `str.ljust` は文字数で埋めるので、日本語ラベルと英字ラベルを混ぜると列が
    揃わない(`配当利回り` は5文字だが10セル、`PER` は3文字で3セル)。
    """
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def _label(text: str, width: int = _LABEL_WIDTH) -> str:
    """表示幅で左詰めする。"""
    return text + " " * max(0, width - _display_width(text))


def _days(days: float, threshold: float) -> str:
    """解消日数。小さすぎて `0.000` に潰れる値を正直に書く。

    大型株では想定ポジションが平均売買代金に対して極小になり、`.3f` では全て
    `0.000` になって情報が消える(7203で実測 1.04e-05日)。
    """
    if days < 0.01:
        shown = "0.01日未満"
    elif days < 1:
        shown = f"{days:.2f}日"
    else:
        shown = f"{days:.1f}日"
    return f"{shown}で解消 (閾値 {threshold:g}日)"


def _pct(value: Decimal | float | None, *, digits: int = 1) -> str:
    """小数をパーセント表記にする。Noneは取得不可と書く(空欄にしない)。"""
    if value is None:
        return _UNAVAILABLE
    return f"{float(value) * 100:.{digits}f}%"


def _num(value: Decimal | float | None, *, digits: int = 2) -> str:
    if value is None:
        return _UNAVAILABLE
    return f"{float(value):.{digits}f}"


def _short(reason: str | None, *, limit: int = 54) -> str:
    if not reason:
        return ""
    text = reason.replace("\n", " ").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _valuation_lines(valuation: ValuationPercentiles | None, kind: InstrumentKind) -> list[str]:
    if valuation is None:
        return [f"  {_label('PER / PBR')}{_UNAVAILABLE} ({kind.value}では算出対象外)"]
    if valuation.unknown_reason is not None:
        return [f"  {_label('PER / PBR')}{_UNAVAILABLE} ({_short(valuation.unknown_reason)})"]

    lines: list[str] = []
    for indicator in valuation.indicators:
        current = _num(indicator.current_value)
        if indicator.percentile is not None:
            # 分位の標本数も出す。分母を黙らせない。
            rank = f"{valuation.window_years}年分位 {_pct(indicator.percentile, digits=0)}  n={indicator.sample_size}"
        else:
            rank = f"分位{_UNAVAILABLE} ({_short(indicator.unknown_reason, limit=40)})"
        lines.append(f"  {_label(indicator.indicator)}{current:>8s}   {rank}")
    return lines


def _dividend_lines(dividend: DividendYieldAssessment) -> list[str]:
    if not dividend.figures:
        return [f"  {_label('配当利回り')}{_UNAVAILABLE} ({_short(dividend.unknown_reason)})"]
    parts: list[str] = []
    notes: list[str] = []
    for figure in dividend.figures:
        # 予想にはラベルを付ける(ルール1)。どの期に対するものかも併記する。
        # 実績は**覆っている月数まで書く。** 「実績」だけだと、半期REITの分配金と
        # 年額配当が同じ顔で並び、読み手は半期の値を年額として読む(2026-11-24)。
        if figure.basis is DividendBasis.FORECAST:
            label = "予想"
        elif figure.basis is DividendBasis.TRAILING_12M:
            label = "実績12か月"
        elif figure.months_covered:
            label = f"実績{figure.months_covered}か月"
        else:
            label = "実績1期"
        period = figure.fiscal_period_end.isoformat() if figure.fiscal_period_end else "期末不明"
        if figure.components:
            amount = "+".join(_num(component, digits=0) for component in figure.components)
            period = f"{period}まで{figure.period_count}期"
        else:
            amount = _num(figure.dividend, digits=0)
        parts.append(f"{label} {_pct(figure.yield_ratio, digits=2)} ({amount}円 / {period})")
        if figure.basis is DividendBasis.TRAILING_PERIOD:
            notes.extend(figure.notes or ("12か月を覆えていない理由が記録されていない",))
    lines = ["  " + _label("配当利回り") + "   ".join(parts)]
    lines += [f"  {_label('')}※ 年額ではない: {_short(note, limit=80)}" for note in notes]
    return lines


def _roe_lines(trend: FinancialTrend) -> list[str]:
    series = [t for t in trend.trends if t.metric_type == _ROE_METRIC]
    if not series:
        return [f"  {_label('ROE')}{_UNAVAILABLE} (可視な観測が無い)"]

    # 会計基準ごとにseriesが分かれる(7203は米国基準4点+IFRS 6点)。
    # 基準をまたいで1本に畳まない——比較可能性が違う。
    points: list[tuple[str, str, str]] = []
    for metric_trend in series:
        standard = metric_trend.accounting_standard or "基準の対応なし"
        for observation in metric_trend.observations:
            if observation.value is None or observation.fiscal_period_end is None:
                continue
            points.append((observation.fiscal_period_end.isoformat(), _pct(observation.value, digits=1), standard))
    if not points:
        return [f"  {_label('ROE')}{_UNAVAILABLE} (値が全て空)"]

    points.sort()
    latest_period, latest_value, latest_standard = points[-1]
    lines = [f"  {_label('ROE')}{latest_value:>8s}   最新 {latest_period} ({latest_standard})"]

    shown_points = points[-_MAX_HISTORY_POINTS:]
    history = " ".join(value for _, value, _ in shown_points)
    span = f"推移(直近{len(shown_points)}/{len(points)}期)" if len(shown_points) < len(points) else f"推移({len(points)}期)"
    standards = sorted({standard for _, _, standard in shown_points})
    suffix = f"  ※基準が複数: {', '.join(standards)}" if len(standards) > 1 else ""
    lines.append(f"    {span} {history}{suffix}")
    return lines


def _forecast_family_lines(series: ForecastRevisionSeries, *, first: bool) -> list[str]:
    """1 family ぶん。familyはラベル列ではなく値側に置く(ラベル列を溢れさせない)。"""
    values = [r for r in series.revisions if r.value is not None]
    per_share = series.metric_family in _PER_SHARE_FAMILIES
    sequence = " → ".join(_num(r.value) if per_share else _yen(r.value) for r in values if r.value is not None)
    target = series.target_fiscal_year_end.isoformat() if series.target_fiscal_year_end else "不明"
    name = _FAMILY_LABELS.get(series.metric_family, series.metric_family)
    head = _label("会社予想") if first else _label("")
    # 改定回数を同じ行に畳む(familyごとに2行使うと1画面を圧迫する)。
    return [f"  {head}{_label(name, 10)}{target}期  {sequence}  (改定{series.revision_count}回/公表{series.observation_count}件)"]


def _forecast_lines(
    forecasts: Sequence[ForecastRevisionSeries],
    *,
    priority: Sequence[str] = _FORECAST_FAMILY_PRIORITY,
    max_families: int = _MAX_FORECAST_FAMILIES,
) -> list[str]:
    """値のある予想を表示順に並べる。

    **familyを固定しない。** 固定すると、その指標だけ空の銘柄で「取得不可」と
    表示され、他にある予想が見えなくなる(2026-11-24に6758と8951で発生)。
    """
    # 各familyについて、判定時点に最も近い将来の決算期を1つ選ぶ。
    by_family: dict[str, ForecastRevisionSeries] = {}
    for candidate in forecasts:
        if candidate.target_fiscal_year_end is None:
            continue
        if not any(r.value is not None for r in candidate.revisions):
            continue
        current = by_family.get(candidate.metric_family)
        if current is None or (candidate.target_fiscal_year_end > (current.target_fiscal_year_end or date.min)):
            by_family[candidate.metric_family] = candidate

    families = [f for f in priority if f in by_family] + sorted(set(by_family) - set(priority))
    if not families:
        return [f"  {_label('会社予想')}{_UNAVAILABLE} (値のある予想が無い)"]

    shown: list[str] = []
    for index, family in enumerate(families[:max_families]):
        shown += _forecast_family_lines(by_family[family], first=index == 0)

    hidden = len(families) - max_families
    note = "※会社予想、実績ではない"
    if hidden > 0:
        note += f" / 他 {hidden} 指標あり (--format json)"
    shown.append(f"  {_label('')}{_label('', 10)}{note}")
    return shown


def _liquidity_line(liquidity: LiquidityAssessment) -> str:
    if liquidity.outcome is LiquidityOutcome.UNKNOWN or liquidity.days_to_liquidate is None:
        return f"  {_label('流動性')}{_UNAVAILABLE} ({_short(liquidity.unknown_reason)})"
    mark = "⚠ " if liquidity.outcome is LiquidityOutcome.WARN else ""
    turnover = liquidity.average_daily_turnover
    turnover_text = f"{turnover / 1e8:.1f}億円/日" if turnover is not None else _UNAVAILABLE
    return (
        f"  {_label('流動性')}{mark}{_days(liquidity.days_to_liquidate, liquidity.threshold_days)}  平均売買代金 {turnover_text}"
    )


def _earnings_line(earnings: EarningsSchedule) -> str:
    if earnings.next_scheduled is None:
        return f"  {_label('次回決算発表')}未公表 ({_short(earnings.unknown_reason)})"
    entry = earnings.next_scheduled
    scheduled = entry.scheduled_on.isoformat() if entry.scheduled_on else "未定"
    quarter = entry.fiscal_quarter or "期種別不明"
    return f"  {_label('次回決算発表')}{scheduled} ({quarter})  公表 {entry.published_on.isoformat()}"


def _per_share_lines(per_share: PerShareComparability) -> list[str]:
    lines: list[str] = []
    for found in per_share.breaks:
        start = found.from_fiscal_period_end.isoformat() if found.from_fiscal_period_end else "?"
        end = found.to_fiscal_period_end.isoformat() if found.to_fiscal_period_end else "?"
        lines.append(
            f"  ⚠ {found.metric_type} の1株当たり基準が {start} → {end} で約{float(found.divisor_ratio):.2f}倍"
            " (分割・併合・増資・訂正のいずれとも断定しない)"
        )
    if per_share.unchecked_metrics:
        lines.append(f"  ・基準の連続性を確認できず: {', '.join(per_share.unchecked_metrics)}")
    if per_share.corporate_actions_known_from is not None and not per_share.corporate_action_dates:
        lines.append(
            f"  ・Corporate Action は {per_share.corporate_actions_known_from.isoformat()} 以降のみ観測"
            " (それ以前は不明、無かったという意味ではない)"
        )
    return lines


def render_entry(
    *,
    code: str,
    instrument_kind: InstrumentKind,
    as_of: datetime,
    trend: FinancialTrend,
    forecasts: Sequence[ForecastRevisionSeries],
    liquidity: LiquidityAssessment,
    dividend: DividendYieldAssessment,
    valuation: ValuationPercentiles | None,
    earnings: EarningsSchedule,
    per_share: PerShareComparability,
) -> list[str]:
    """1銘柄ぶんの1画面。評価語を付けず、数字と警告だけを並べる。"""
    lines = [
        f"{code}  {instrument_kind.value}  {as_of.isoformat(timespec='minutes')} 時点",
        "-" * 78,
    ]
    lines += _valuation_lines(valuation, instrument_kind)
    lines += _dividend_lines(dividend)
    lines += _roe_lines(trend)
    lines += _forecast_lines(forecasts)
    lines.append(_liquidity_line(liquidity))
    lines.append(_earnings_line(earnings))
    warnings = _per_share_lines(per_share)
    if warnings:
        lines.append("")
        lines += warnings
    return lines


def render_report(
    *,
    as_of: datetime,
    entries: Sequence[Sequence[str]],
    correlation: CorrelationAssessment | None,
    unavailable: Sequence[str],
) -> str:
    """銘柄ごとの画面と、銘柄をまたぐ警告をまとめる。"""
    blocks: list[str] = []
    for entry in entries:
        blocks.append("\n".join(entry))

    tail: list[str] = []
    if correlation is not None and correlation.pairs:
        tail.append("=" * 78)
        tail.append(f"相関 (閾値 {correlation.threshold}, {correlation.window_sessions}営業日)")
        # **全ペアの係数を出す。** 閾値超えだけを出すと 0.68 と 0.05 が同じ
        # 「超えるペアなし」になり、分散させる意味があるかの判断に使えない
        # (2026-11-24、物流REIT3本を並べたときに気づいた)。
        for pair in correlation.pairs:
            if pair.outcome is CorrelationOutcome.UNKNOWN:
                tail.append(f"  ・{pair.code_a} / {pair.code_b}  {_UNAVAILABLE} ({_short(pair.unknown_reason, limit=40)})")
                continue
            mark = "⚠" if pair.outcome is CorrelationOutcome.WARN else " "
            tail.append(f"  {mark} {pair.code_a} / {pair.code_b}  {_num(pair.correlation)}  n={pair.overlapping_returns}")
        if not any(p.outcome is CorrelationOutcome.WARN for p in correlation.pairs):
            tail.append(f"  閾値 {correlation.threshold} を超えるペアなし")

    if unavailable:
        tail.append("=" * 78)
        tail.append(f"このスクリーナーが出さない指標: {', '.join(unavailable)}")

    return "\n\n".join(blocks) + ("\n" + "\n".join(tail) if tail else "")
