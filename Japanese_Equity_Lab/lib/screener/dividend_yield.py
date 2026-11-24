"""配当利回り(現在値のみ)。

方針書 Step 3 の出力項目のうち、**どのEndpointにも存在しない唯一の指標**。
`/equities/valuation` の11項目にも含まれないので、出すなら必ず導出になる
(`JQUANTS_V2_STEP3_SOURCE_ONBOARDING.md` §10)。

## 分子は「1年分」でなければならない

Providerの実績Fieldは期ごとの値である。`DivAnn`(一株当たり配当)は年次決算の
Fieldなので1年分が入るが、`DivUnit`(1口当たり分配金)は**その決算期の分**であり、
半期決算のREITでは半年分しか入らない。

これを同じ「実績」ラベルで株価に割ると、**半期REITの利回りが約半分に見える。**
実例: 3283(日本プロロジスリート、5月期/11月期)は `1716 / 81900 = 2.10%` と
出ていたが、市場が語る水準は4%台である(2026-11-24に実データで確認)。
**取得できている値を、取得できていない値のように見せていた**わけではなく、
別の量を同じ名前で見せていた。後者のほうが気づきにくい。

### ×2しない

半期を倍にするのは、取得できない値を計算で埋める行為(ルートCLAUDE.md 規約3)。
J-REITのDPUは物件売却益で期ごとに凸凹し、決算期数も銘柄で一律とは限らない。
代わりに**開示済みの連続する期を合算する。** これは実績の足し算であって推測ではない。

### 合算は期をまたぐので、段差を踏む

「現在値は分割の段差を踏まない」という当初の論拠は、**1点だけを採る限り**成り立つ。
合算は複数期にまたがるので成り立たない。一株当たり配当は**開示時点のままで
遡及調整されない**(公式明記)ため、合算する期の間に分割・併合があれば和は無意味になる。

そこで合算には門を2つ置く:

1. **期がちょうど12か月をタイル状に覆うこと。** 期末日の間隔が一定で、
   その間隔 × 期数 = 12か月であることを確認する。隙間・重複があれば合算しない。
2. **合算する期の間に基準の不連続がないこと。** `lib/screener/per_share.py` が
   EPS・BPSで検知した不連続の期末を受け取り、窓の内側に落ちていれば合算しない。
   REITでEPSの除数は口数なので、DPUと除数を共有する。ただし
   **これは観測された不連続の利用であって、分割があったという断定ではない。**

どちらかが通らなければ `TRAILING_PERIOD` として**期の長さを明示して1期分だけ出す。**
年換算は人間に残す。空欄にも0にもしない。

## 予想と実績を両方出し、どちらかを黙って選ばない

市場慣行の「配当利回り」は**予想**配当ベースだが、実績ベースも成り立つ。
片方が無いときにもう片方へ暗黙に落とすと、**同じ名前で別の量を出すことになる。**
そこで両方を基準ラベル付きで並べ、無いものは無いと言う。

なおREITでは当期予想スロット(`FDivUnit`)が常に
`TARGET_YEAR_ALREADY_REPORTED` で閉じ、翌期予想がどのFieldに入るかは未確認である
(`lib/fundamentals/normalize.py` の `distribution_per_unit` 注記)。
したがってREITの予想利回りは現状出ない。これはSource側の未確認事項であり、
`NxFDivUnit` 等を**推測でmappingして埋めてはならない。**

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
from calendar import monthrange
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from lib.screener.financial_trend import FinancialTrend
from lib.screener.forecast_revisions import ForecastRevisionSeries, metric_family
from lib.screener.instrument import InstrumentKind

logger = logging.getLogger(__name__)

TRAILING_MONTHS = 12
"""実績利回りの分子が覆うべき月数。"""

_ANNUAL_BY_FIELD_DEFINITION = frozenset({"dividend_per_share_annual"})
"""Field定義そのものが年額である指標族。

`DivAnn`/`FDivAnn` は「年間配当」を表すFieldなので、1期分でも12か月を覆う。
`DivUnit` はそうではない。**族名を見て決め、値の大きさから推測しない。**
"""


class DividendBasis(StrEnum):
    """利回りの分子が何か。**同じ指標の3つの測定値ではなく、別の量である。**"""

    FORECAST = "FORECAST"
    """当期の会社予想配当。市場慣行の「配当利回り」はこちら。"""
    TRAILING_12M = "TRAILING_12M"
    """直近12か月を覆う、開示済み実績配当。1期で覆える場合も含む。"""
    TRAILING_PERIOD = "TRAILING_PERIOD"
    """1期分の実績配当。**年額ではない。** 12か月を覆えなかったときの退避先。"""


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
    period_count: int = 1
    """分子に含まれる決算期の数。"""
    months_covered: int | None = None
    """分子が覆う月数。確認できなければNone。**12と仮定しない。**"""
    components: tuple[Decimal, ...] = ()
    """合算した期ごとの値(古い順)。2期以上を足したときだけ入る。"""
    notes: tuple[str, ...] = ()
    """この分子についての留保(12か月に出来なかった理由など)。"""


@dataclass(frozen=True, kw_only=True)
class DividendHistoryPoint:
    """1決算期ぶんの実績配当。"""

    fiscal_period_end: date
    value: Decimal
    basis_break_before: bool
    """直前の期との間に1口/1株当たり基準の不連続があるか。

    **印を付けずに並べてはならない。** 分割をまたいだ約3倍の段差は、
    印が無ければ「分配金が3倍になった」と読める。
    """


@dataclass(frozen=True, kw_only=True)
class DividendYieldAssessment:
    code: str
    instrument_kind: InstrumentKind
    price: Decimal | None
    price_session: date | None
    figures: tuple[DividendYieldFigure, ...]
    unknown_reason: str | None
    """何も出せなかった理由。空欄にせず明示する(ルートCLAUDE.md)。"""
    history: tuple[DividendHistoryPoint, ...] = ()
    """実績配当の期別推移(古い順)。切り詰めは表示側の仕事。

    合算した直近2期だけでは「直近の減少が初めてか、何度目か」が分からない。
    REITではDPUの推移がROEより中心的な系列なので、全期を持ち上げる。
    """

    @property
    def forecast(self) -> DividendYieldFigure | None:
        return next((f for f in self.figures if f.basis is DividendBasis.FORECAST), None)

    @property
    def trailing(self) -> DividendYieldFigure | None:
        return next(
            (f for f in self.figures if f.basis in (DividendBasis.TRAILING_12M, DividendBasis.TRAILING_PERIOD)),
            None,
        )


def _is_month_end(value: date) -> bool:
    return value.day == monthrange(value.year, value.month)[1]


def _month_span(earlier: date, later: date) -> int | None:
    """期末日どうしの間隔を月で返す。対応が取れなければNone。

    期末は月末であることが多い(5/31と11/30)。日数で比べると同じ「半年」が
    182日とも184日とも出るので月で数える。月末どうし、または同じ日どうしの
    ときだけ意味を認め、**それ以外は不明として扱う(近い方へ丸めない)。**
    """
    months = (later.year - earlier.year) * 12 + (later.month - earlier.month)
    if months <= 0:
        return None
    if _is_month_end(earlier) and _is_month_end(later):
        return months
    if earlier.day == later.day:
        return months
    return None


def _months_before(value: date, months: int) -> date:
    total = value.year * 12 + (value.month - 1) - months
    year, month_index = divmod(total, 12)
    month = month_index + 1
    if _is_month_end(value):
        return date(year, month, monthrange(year, month)[1])
    return date(year, month, min(value.day, monthrange(year, month)[1]))


def _actual_by_period(trend: FinancialTrend, metric_type: str) -> dict[date, tuple[Decimal, datetime | None]]:
    """決算期末 → (値, 開示時刻)。

    `build_financial_trend` が既にPITで絞り、Versionも最新を採っている。
    同じ指標が会計基準ごとに複数seriesへ分かれるので、同じ期末が重なったときは
    **開示が新しい方**を採る(基準をまたいで値を合成しない。1点を選ぶだけ)。
    """
    out: dict[date, tuple[Decimal, datetime | None]] = {}
    for series in trend.trends:
        if series.metric_type != metric_type:
            continue
        for obs in series.observations:
            if obs.value is None or obs.fiscal_period_end is None:
                continue
            existing = out.get(obs.fiscal_period_end)
            if existing is None:
                out[obs.fiscal_period_end] = (obs.value, obs.published_at)
                continue
            if obs.published_at is not None and (existing[1] is None or obs.published_at > existing[1]):
                out[obs.fiscal_period_end] = (obs.value, obs.published_at)
    return out


def _build_history(
    by_period: Mapping[date, tuple[Decimal, datetime | None]],
    *,
    basis_break_period_ends: frozenset[date],
) -> tuple[DividendHistoryPoint, ...]:
    ends = sorted(by_period)
    return tuple(
        DividendHistoryPoint(
            fiscal_period_end=end,
            value=by_period[end][0],
            # 先頭の点には「直前」が無い。不連続の遷移先が先頭なら、
            # 比較対象がこの系列の外にあるので印を立てない。
            basis_break_before=index > 0 and end in basis_break_period_ends,
        )
        for index, end in enumerate(ends)
    )


@dataclass(frozen=True, kw_only=True)
class _Trailing:
    total: Decimal
    components: tuple[Decimal, ...]
    period_ends: tuple[date, ...]
    months_covered: int | None
    published_at: datetime | None
    notes: tuple[str, ...]


def _build_trailing(
    by_period: Mapping[date, tuple[Decimal, datetime | None]],
    *,
    basis_break_period_ends: frozenset[date],
    annual_by_definition: bool,
) -> _Trailing | None:
    """直近12か月を覆う実績配当。覆えないときは1期分と理由を返す。

    合算できない理由は**捨てずに持ち上げる。** 「なぜ年額でないのか」が
    表示に出なければ、読み手は半期の値を年額として読む。
    """
    if not by_period:
        return None

    latest = max(by_period)

    def _one_period(months: int | None, reason: str) -> _Trailing:
        value, published_at = by_period[latest]
        return _Trailing(
            total=value,
            components=(),
            period_ends=(latest,),
            months_covered=months,
            published_at=published_at,
            notes=(reason,),
        )

    if annual_by_definition:
        # `DivAnn` は「年間配当」を表すFieldなので、1期で12か月を覆う。
        # これはField定義から言えることで、期末の並びからの推測ではない。
        value, published_at = by_period[latest]
        return _Trailing(
            total=value,
            components=(),
            period_ends=(latest,),
            months_covered=TRAILING_MONTHS,
            published_at=published_at,
            notes=(),
        )

    # 期ごとのField(`DivUnit`)では、期の長さを**観測された期末の間隔から**決める。
    # 窓の中に1期しか無いことを「その1期が12か月」の根拠にしてはならない。
    # **他の期が見えないことは、その期が長いことの証拠ではない。**
    # (2026-11-24の回帰。存在しないField名が0件を返したのを「開示していない」と
    #  読みかけたのと同じ形。)
    all_ends = sorted(by_period)
    if len(all_ends) < 2:
        return _one_period(None, "決算期が1つしか可視でないため期の長さを確認できない")
    period_months = _month_span(all_ends[-2], all_ends[-1])
    if period_months is None:
        return _one_period(None, "直近2期の期末の間隔を月で数えられない")

    window_start = _months_before(latest, TRAILING_MONTHS)
    ends = sorted(end for end in by_period if window_start < end <= latest)
    if period_months * len(ends) != TRAILING_MONTHS:
        return _one_period(
            period_months,
            f"開示済みの期が12か月を覆わないため合算しない({period_months}か月 × {len(ends)}期)",
        )

    boundaries = (window_start, *ends[:-1])
    spans = [_month_span(start, end) for start, end in zip(boundaries, ends, strict=True)]
    if any(span != period_months for span in spans):
        return _one_period(period_months, f"決算期の長さが揃わないため合算しない(間隔={spans}か月)")

    crossed = [end for end in ends[1:] if end in basis_break_period_ends]
    if crossed:
        joined = ", ".join(end.isoformat() for end in crossed)
        return _one_period(
            period_months,
            f"合算する期の間に1口/1株当たり基準の不連続があるため合算しない({joined})",
        )

    components = tuple(by_period[end][0] for end in ends)
    published: list[datetime] = [at for at in (by_period[end][1] for end in ends) if at is not None]
    return _Trailing(
        total=sum(components, Decimal(0)),
        components=components if len(components) > 1 else (),
        period_ends=tuple(ends),
        months_covered=TRAILING_MONTHS,
        published_at=max(published) if published else None,
        notes=(),
    )


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
    basis_break_period_ends: frozenset[date] = frozenset(),
) -> DividendYieldAssessment:
    """配当利回りの現在値を、基準ラベル付きで出す。

    `basis_break_period_ends` は `lib/screener/per_share.py` が検知した不連続の
    遷移先期末。渡さなければ合算の門が1つ(期のタイル)だけになるので、
    **呼び出し側は渡すこと。**

    株価が無い、配当が無い、銘柄種別が対象外——いずれも `figures` を空にして
    `unknown_reason` を埋める。**0や空欄にしない。**
    """

    resolved_price = _to_decimal_price(price)

    def _empty(reason: str, history: tuple[DividendHistoryPoint, ...] = ()) -> DividendYieldAssessment:
        return DividendYieldAssessment(
            code=code,
            instrument_kind=instrument_kind,
            price=resolved_price,
            price_session=price_session,
            figures=(),
            unknown_reason=reason,
            history=history,
        )

    metric_type = _ACTUAL_METRIC_BY_KIND.get(instrument_kind)
    if metric_type is None:
        return _empty(f"InstrumentKind={instrument_kind.value} ではどの配当Fieldが適切か確認していないため算出しない")

    # 推移は株価に依らない。**利回りが出せなくても推移は出す。**
    by_period = _actual_by_period(actual_trend, metric_type)
    history = _build_history(by_period, basis_break_period_ends=basis_break_period_ends)

    if resolved_price is None:
        return _empty("株価が取得できないため算出できない", history)
    if resolved_price <= 0:
        return _empty(f"株価が正の値でないため算出できない(price={resolved_price})", history)

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
                months_covered=TRAILING_MONTHS if family in _ANNUAL_BY_FIELD_DEFINITION else None,
            )
        )

    trailing = _build_trailing(
        by_period,
        basis_break_period_ends=basis_break_period_ends,
        annual_by_definition=family in _ANNUAL_BY_FIELD_DEFINITION,
    )
    if trailing is not None:
        annualized = trailing.months_covered == TRAILING_MONTHS and not trailing.notes
        figures.append(
            DividendYieldFigure(
                basis=DividendBasis.TRAILING_12M if annualized else DividendBasis.TRAILING_PERIOD,
                source_metric_type=metric_type,
                dividend=trailing.total,
                yield_ratio=trailing.total / resolved_price,
                fiscal_period_end=trailing.period_ends[-1],
                published_at=trailing.published_at,
                period_count=len(trailing.period_ends),
                months_covered=trailing.months_covered,
                components=trailing.components,
                notes=trailing.notes,
            )
        )

    if not figures:
        return _empty(f"{metric_type} の予想・実績いずれも判定時点で可視でない", history)

    logger.info("screener: %s dividend yield from %d basis/bases", code, len(figures))
    return DividendYieldAssessment(
        code=code,
        instrument_kind=instrument_kind,
        price=resolved_price,
        price_session=price_session,
        figures=tuple(figures),
        unknown_reason=None,
        history=history,
    )
