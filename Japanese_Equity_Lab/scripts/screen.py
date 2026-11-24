"""銘柄ざっと見スクリーナー(Step 3、読み取り専用)。

銘柄コードを渡すと、1回の実行で次を出す。

- 実績財務の年次推移(売上・営業利益・経常利益・純利益・EPS・総資産)
- 会社予想の改定履歴(いつ・どちら向きに・何%)
- 流動性と相関の警告(Step 1、`lib/pretrade_risk`)
- 1株当たり指標の比較可能性(`per_share_comparability`)

実績は**開示時点のまま**で、株式分割をさかのぼって調整していない(株価側は調整
する)。この非対称性でEPSの推移を読み違えないよう、基準が切り替わった境界を
`per_share_comparability.breaks` に出す。値は補正しない。

推奨判定・スコアリング・自動ランキングは行わない。最終的なBUY/HOLD/SELL判断は
必ず人間が行う(`CLAUDE.md`)。

**出さないもの**: PBR・配当利回り・ROE。`lib/fundamentals/normalize.py` の通り
Share Count関連・Dividend関連・`ROE` はRaw PayloadにはあるがMetricへ未マッピング
で、Field名を推測して読むことは禁止されている。出力の `unavailable` で明示する。
PER分位は `lib/valuation` にモデルがあるがOrchestrationが未整備(未着手)。

PIT:

- `--as-of` 省略時の判定時点は「いま(JST)」。暦日の終わりを仮定しない。
- 株価側は `lib/pretrade_risk/window.py` が大引け未到来セッションを除外する。
- 財務側の可視性は `MARKET_PUBLIC_AT`(市場参加者がいつ知り得たか)を既定とする。
  `PROVIDER_AVAILABLE_AT` はPhase4Aでは `availability_basis` が常に `UNKNOWN` で
  結果が空になるため、`--provider-semantics` と
  `--include-unknown-availability` を明示した場合のみ使う。
  どちらで解決したかは出力の `availability_semantics` に必ず載せる。

実行例:
    python scripts/screen.py --codes 7203 6758 --position-value 1000000
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

sys.dont_write_bytecode = True
_LAB_DIR = Path(__file__).resolve().parents[1]
_REPO_ROOT = _LAB_DIR.parent
sys.path.insert(0, str(_LAB_DIR))

from dotenv import load_dotenv  # noqa: E402
from lib.backtest.price_history import AsOfAdjustedPriceHistory  # noqa: E402
from lib.cli_io import force_output_encoding  # noqa: E402
from lib.data_sources.convert import (  # noqa: E402
    detect_corporate_action_events_from_equity_bars,
    equity_bars_payload_to_raw_bars,
)
from lib.data_sources.jquants import JQuantsAdapter  # noqa: E402
from lib.data_sources.ticker_codes import (  # noqa: E402
    TickerCodeNormalizationError,
    normalize_provider_code_to_internal,
)
from lib.errors import DataSourceError  # noqa: E402
from lib.evidence.model import AvailabilitySemantics  # noqa: E402
from lib.fundamentals.model import DisclosureEnvelope, FundamentalMetric  # noqa: E402
from lib.fundamentals.normalize import build_revision_histories, parse_financial_summary_payload  # noqa: E402
from lib.market_calendar import JST, session_close_at  # noqa: E402
from lib.pretrade_risk import assess_correlation, assess_liquidity  # noqa: E402
from lib.pretrade_risk.liquidity import DEFAULT_MAX_STALENESS_DAYS, LiquidityOutcome  # noqa: E402
from lib.schemas.price_data import CorporateAction, RawOHLCVBar  # noqa: E402
from lib.screener import (  # noqa: E402
    InstrumentKind,
    assess_dividend_yield,
    assess_per_share_comparability,
    assess_valuation_percentiles,
    build_earnings_schedule,
    build_financial_trend,
    build_forecast_revision_series,
    classify_codes,
)
from lib.screener.financial_trend import UNMAPPED_METRICS  # noqa: E402

logger = logging.getLogger(__name__)

PRICE_FETCH_MARGIN_DAYS = 600
FINS_FETCH_MARGIN_DAYS = 4000  # 約11年。通期実績を10年ぶん拾うための余裕。
TREND_METRIC_TYPES = (
    "sales",
    "operating_profit",
    "ordinary_profit",
    "net_profit",
    "eps",
    "total_assets",
    # Step 3 Stage 4a(2026-11-24)。方針書の出力仕様「ROEの10年推移」。
    # ProviderがFY開示にのみ入れるので、年次で1点ずつ並ぶ(7203: 11/41行)。
    "provider_reported_roe",
    # per_share.py がBPSの不連続を検知するのに必要(除数は自己資本)。
    "bps",
    "provider_reported_sheq",
)

DIVIDEND_ACTUAL_METRIC_TYPES = ("dividend_per_share_annual", "distribution_per_unit")
"""配当利回りの実績ベース用。表示する推移とは別に取る。

`TREND_METRIC_TYPES` に混ぜると、方針書が指定した推移の中身が膨らんで
「ざっと見」でなくなる。PIT絞りは同じ `build_financial_trend` を使い回す。
"""


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--codes", nargs="+", required=True, help="銘柄コード(スペース区切り)")
    parser.add_argument("--position-value", type=float, default=1_000_000.0, help="流動性判定に使う想定ポジション額(円)")
    parser.add_argument("--as-of", type=date.fromisoformat, default=None, help="判定日(YYYY-MM-DD)。既定はいま(JST)")
    parser.add_argument("--years", type=int, default=10, help="財務推移をさかのぼる年数")
    parser.add_argument("--forecast-years", type=int, default=3, help="予想改定履歴を出す対象決算期の数(新しい順)")
    parser.add_argument("--max-staleness-days", type=int, default=DEFAULT_MAX_STALENESS_DAYS)
    parser.add_argument(
        "--provider-semantics",
        action="store_true",
        help="財務の可視性をPROVIDER_AVAILABLE_ATで解決する(既定はMARKET_PUBLIC_AT)",
    )
    parser.add_argument(
        "--include-unknown-availability",
        action="store_true",
        help="availability_basisがUNKNOWNのVersionも含める(PROVIDER_AVAILABLE_AT時のみ作用)",
    )
    return parser.parse_args(argv)


def _fail(status: str, detail: str) -> int:
    print(json.dumps({"status": status, "detail": detail}, ensure_ascii=False), file=sys.stderr)
    return 2


def _num(value: Decimal | float | None) -> float | None:
    return None if value is None else float(value)


def main(argv: list[str] | None = None) -> int:
    # リダイレクト時のcp932符号化エラーを防ぐ。BOMは付けない(json.loadが壊れる)
    force_output_encoding()
    args = _parse_args(argv)
    load_dotenv(_REPO_ROOT / ".env")

    try:
        normalized = [normalize_provider_code_to_internal(c) for c in args.codes]
    except TickerCodeNormalizationError as exc:
        return _fail("INVALID_CODE", str(exc))
    codes = list(dict.fromkeys(normalized))

    now = datetime.now(JST)
    as_of = session_close_at(args.as_of) if args.as_of is not None else now
    if as_of > now:
        return _fail("AS_OF_IN_FUTURE", f"as_of {as_of.isoformat()} is after now {now.isoformat()}")

    semantics = AvailabilitySemantics.PROVIDER_AVAILABLE_AT if args.provider_semantics else AvailabilitySemantics.MARKET_PUBLIC_AT

    adapter = JQuantsAdapter()
    try:
        bars_result = adapter.fetch_equity_bars(
            codes=codes,
            start_date=as_of.date() - timedelta(days=PRICE_FETCH_MARGIN_DAYS),
            end_date=as_of.date(),
        )
        fins_result = adapter.fetch_financial_statements(
            codes=codes,
            start_date=as_of.date() - timedelta(days=FINS_FETCH_MARGIN_DAYS),
            end_date=as_of.date(),
        )
    except DataSourceError as exc:
        return _fail("DATA_SOURCE_UNAVAILABLE", str(exc))

    if as_of > bars_result.retrieved_at:
        return _fail(
            "AS_OF_AFTER_RETRIEVAL",
            f"as_of {as_of.isoformat()} is after retrieved_at {bars_result.retrieved_at.isoformat()}",
        )

    raw_bars = equity_bars_payload_to_raw_bars(bars_result.payload)
    events = detect_corporate_action_events_from_equity_bars(bars_result.payload)
    # 型を書かないと中身がAnyになり、Barのフィールド型がmypyから消える。
    # 2026-11-24、配当利回りで実際にそれが起きた(close: float|None を
    # Decimal|None の引数へ渡してもmypyが通った)。
    raw_by_code: dict[str, list[RawOHLCVBar]] = {c: [] for c in codes}
    for bar in raw_bars:
        raw_by_code.setdefault(bar.code, []).append(bar)
    events_by_code: dict[str, list[CorporateAction]] = {c: [] for c in codes}
    for event in events:
        events_by_code.setdefault(event.code, []).append(event)
    price_source = AsOfAdjustedPriceHistory(raw_by_code, events_by_code)

    envelopes, metrics = parse_financial_summary_payload(fins_result.payload, retrieved_at=fins_result.retrieved_at)
    envelopes_by_code: dict[str, list[DisclosureEnvelope]] = {c: [] for c in codes}
    for envelope in envelopes:
        envelopes_by_code.setdefault(envelope.internal_code, []).append(envelope)
    envelope_code = {e.envelope_id: e.internal_code for e in envelopes}
    metrics_by_code: dict[str, list[FundamentalMetric]] = {c: [] for c in codes}
    for metric in metrics:
        code = envelope_code.get(metric.envelope_id)
        if code is not None:
            metrics_by_code.setdefault(code, []).append(metric)

    cutoff = date(as_of.year - args.years, as_of.month, as_of.day)

    # 銘柄種別。**値を見てからソースを選ばないため、取得前に決め打ちする**
    # (lib/screener/instrument.py)。
    master_unavailable_reason: str | None = None
    try:
        master_payload = adapter.fetch_equities_master(as_of=as_of.date()).payload
    except DataSourceError as exc:
        master_unavailable_reason = str(exc)
        logger.warning("screener: /equities/master が取得できずInstrumentKindは全てUNKNOWNです: %s", exc)
        master_payload = []
    instrument_kinds = classify_codes(codes=codes, master_payload=master_payload)

    # Stage 4b。valuationはREITでMktCap以外すべてnullなので、REITには引かない
    # ——nullを見てから切り替えるのではなく、種別で先に決める。
    valuation_codes = [c for c in codes if instrument_kinds.get(c) is InstrumentKind.SHARE]
    valuation_rows: list[dict[str, object]] = []
    valuation_unavailable_reason: str | None = None
    if valuation_codes:
        try:
            valuation_rows = list(adapter.fetch_valuation_indicators(codes=valuation_codes).payload)
        except DataSourceError as exc:
            valuation_unavailable_reason = str(exc)
            logger.warning("screener: /equities/valuation が取得できません: %s", exc)

    earnings_rows: list[dict[str, object]] = []
    earnings_unavailable_reason: str | None = None
    try:
        earnings_rows = list(adapter.fetch_earnings_dates(codes=codes).payload)
    except DataSourceError as exc:
        earnings_unavailable_reason = str(exc)
        logger.warning("screener: /fins/earnings-date が取得できません: %s", exc)

    entries = []
    # 警告の集計はdataclassから直接取る。整形済みJSONを読み返して判定しない。
    liquidity_warned: list[str] = []
    per_share_warned: list[str] = []
    for code in codes:
        code_metrics = metrics_by_code.get(code, [])
        histories = build_revision_histories(envelopes_by_code.get(code, []), code_metrics)

        trend = build_financial_trend(
            code=code,
            envelopes=envelopes_by_code.get(code, []),
            metrics=code_metrics,
            revision_histories=histories,
            decision_at=as_of,
            availability_semantics=semantics,
            metric_types=TREND_METRIC_TYPES,
            include_unknown_availability=args.include_unknown_availability,
        )
        forecasts = build_forecast_revision_series(
            revision_histories=histories,
            metrics=code_metrics,
            envelopes=envelopes_by_code.get(code, []),
            decision_at=as_of,
            availability_semantics=semantics,
            include_unknown_availability=args.include_unknown_availability,
        )
        # 対象決算期が新しい順に、直近 --forecast-years 期ぶんだけ残す。
        # 全期を出すと1銘柄で数千行になり「ざっと見」にならない。
        known_targets = sorted(
            {s.target_fiscal_year_end for s in forecasts if s.target_fiscal_year_end is not None}, reverse=True
        )
        kept_targets = set(known_targets[: args.forecast_years])
        forecasts = tuple(s for s in forecasts if s.target_fiscal_year_end in kept_targets)
        # 会計基準上そもそも存在しない指標は、改定履歴として並べても中身が無い。
        # 取得不可とも違うので別枠へ移す(IFRS採用銘柄の経常利益など)。
        not_applicable_families = sorted({s.metric_family for s in forecasts if s.is_not_applicable_under_standard})
        forecasts = tuple(s for s in forecasts if not s.is_not_applicable_under_standard)

        dividend_trend = build_financial_trend(
            code=code,
            envelopes=envelopes_by_code.get(code, []),
            metrics=code_metrics,
            revision_histories=histories,
            decision_at=as_of,
            availability_semantics=semantics,
            metric_types=DIVIDEND_ACTUAL_METRIC_TYPES,
            include_unknown_availability=args.include_unknown_availability,
        )
        latest_bar = max(
            (b for b in raw_by_code.get(code, []) if session_close_at(b.session_date) <= as_of),
            key=lambda b: b.session_date,
            default=None,
        )
        dividend = assess_dividend_yield(
            code=code,
            instrument_kind=instrument_kinds.get(code, InstrumentKind.UNKNOWN),
            price=latest_bar.close if latest_bar is not None else None,
            price_session=latest_bar.session_date if latest_bar is not None else None,
            actual_trend=dividend_trend,
            forecast_series=forecasts,
            decision_at=as_of,
        )

        valuation = (
            assess_valuation_percentiles(code=code, rows=valuation_rows, decision_at=as_of, window_years=args.years)
            if instrument_kinds.get(code) is InstrumentKind.SHARE
            else None
        )
        earnings = build_earnings_schedule(code=code, rows=earnings_rows, decision_at=as_of)

        code_bars = raw_by_code.get(code, [])
        per_share = assess_per_share_comparability(
            code=code,
            trend=trend,
            corporate_actions=events_by_code.get(code, []),
            corporate_actions_known_from=min((b.session_date for b in code_bars), default=None),
        )
        liquidity = assess_liquidity(
            source=price_source,
            code=code,
            position_value=args.position_value,
            as_of=as_of,
            max_staleness_days=args.max_staleness_days,
        )
        if liquidity.outcome is LiquidityOutcome.WARN:
            liquidity_warned.append(code)
        if per_share.breaks:
            per_share_warned.append(code)

        entries.append(
            {
                "code": code,
                "liquidity": {
                    "outcome": liquidity.outcome.value,
                    "average_daily_turnover": liquidity.average_daily_turnover,
                    "days_to_liquidate": liquidity.days_to_liquidate,
                    "last_session": liquidity.last_session.isoformat() if liquidity.last_session else None,
                    "staleness_days": liquidity.staleness_days,
                    "unknown_reason": liquidity.unknown_reason,
                },
                "financial_trend": [
                    {
                        "metric_type": t.metric_type,
                        "accounting_standard": t.accounting_standard,
                        "observations": [
                            {
                                "fiscal_period_end": o.fiscal_period_end.isoformat() if o.fiscal_period_end else None,
                                "value": _num(o.value),
                                "published_at": o.published_at.isoformat() if o.published_at else None,
                                "superseded_count": o.superseded_count,
                            }
                            for o in t.observations
                            if o.fiscal_period_end is None or o.fiscal_period_end >= cutoff
                        ],
                    }
                    for t in trend.trends
                ],
                "instrument_kind": instrument_kinds.get(code, InstrumentKind.UNKNOWN).value,
                "valuation_percentiles": (
                    {
                        "window_years": valuation.window_years,
                        "window_start": valuation.window_start.isoformat(),
                        "current_session": (valuation.current_session.isoformat() if valuation.current_session else None),
                        "staleness_days": valuation.staleness_days,
                        "unknown_reason": valuation.unknown_reason,
                        "indicators": [
                            {
                                "indicator": i.indicator,
                                "current_value": _num(i.current_value),
                                "percentile": _num(i.percentile),
                                "sample_size": i.sample_size,
                                "excluded_non_positive": i.excluded_non_positive,
                                "excluded_missing": i.excluded_missing,
                                "first_session": (i.first_session.isoformat() if i.first_session else None),
                                "last_session": (i.last_session.isoformat() if i.last_session else None),
                                "unknown_reason": i.unknown_reason,
                            }
                            for i in valuation.indicators
                        ],
                        "note": (
                            "percentileは経験分布関数 count(x<=現在値)/n の小数(0.23=下から23%)。"
                            "非正の値は分布から除外し件数を excluded_non_positive に出す"
                            "(負のPERは「安い」ではなく「赤字」)。現在値が非正なら分位はUNKNOWN。"
                            "PER・PBRは権利落ち日で株価と一株当たり価値が打ち消し合うため分割の処理は不要。"
                        ),
                    }
                    if valuation is not None
                    else {
                        "unknown_reason": (
                            "InstrumentKind="
                            + instrument_kinds.get(code, InstrumentKind.UNKNOWN).value
                            + " では/equities/valuationがMktCap以外を返さないため算出しない"
                        ),
                        "indicators": [],
                    }
                ),
                "earnings_schedule": {
                    "next_scheduled": (
                        {
                            "scheduled_on": (
                                earnings.next_scheduled.scheduled_on.isoformat() if earnings.next_scheduled.scheduled_on else None
                            ),
                            "published_on": earnings.next_scheduled.published_on.isoformat(),
                            "fiscal_quarter": earnings.next_scheduled.fiscal_quarter,
                            "fiscal_year_end": earnings.next_scheduled.fiscal_year_end,
                        }
                        if earnings.next_scheduled is not None
                        else None
                    ),
                    "restatements_of_the_same_date": earnings.restatements_of_the_same_date,
                    "visible_entry_count": len(earnings.entries),
                    "unknown_reason": earnings.unknown_reason,
                    "note": (
                        "予定日は改定されるので(公表日, 予定日)の対を全て保持する。"
                        "予定日での検索は訂正前が消えるため使わない(PubDate基準で可視性を判定)。"
                        "決算期を識別するFieldが無い(FYEはMMDDで年を含まない)ため、"
                        "決算期ごとの改定回数は数えられない。同一予定日の再報告のみ数える。"
                        "next_scheduledがnullなのは、次の予定日がまだ公表されていない正常な状態でもある。"
                    ),
                },
                "dividend_yield": {
                    "price": _num(dividend.price),
                    "price_session": (dividend.price_session.isoformat() if dividend.price_session else None),
                    "unknown_reason": dividend.unknown_reason,
                    "figures": [
                        {
                            "basis": f.basis.value,
                            "source_metric_type": f.source_metric_type,
                            "dividend": _num(f.dividend),
                            "yield_ratio": _num(f.yield_ratio),
                            "fiscal_period_end": (f.fiscal_period_end.isoformat() if f.fiscal_period_end else None),
                            "published_at": (f.published_at.isoformat() if f.published_at else None),
                        }
                        for f in dividend.figures
                    ],
                    "note": (
                        "予想と実績は別の量なので両方を並べる。片方が無いときもう片方へ"
                        "暗黙に落とさない。yield_ratioは小数(0.0312=3.12%)。"
                        "一株当たり配当は分割の遡及調整がされないが、現在値は最新の配当と"
                        "最新の株価で期をまたがないため段差を踏まない(分位は踏むので出さない)。"
                    ),
                },
                "per_share_comparability": {
                    "metrics": list(per_share.per_share_metrics),
                    "divisor_sources": {m: src for m, src in per_share.divisor_sources},
                    "tolerance": float(per_share.tolerance),
                    "corporate_action_dates": [d.isoformat() for d in per_share.corporate_action_dates],
                    "corporate_actions_known_from": (
                        per_share.corporate_actions_known_from.isoformat() if per_share.corporate_actions_known_from else None
                    ),
                    "unchecked_metrics": list(per_share.unchecked_metrics),
                    "breaks": [
                        {
                            "metric_type": b.metric_type,
                            "accounting_standard": b.accounting_standard,
                            "from_fiscal_period_end": (
                                b.from_fiscal_period_end.isoformat() if b.from_fiscal_period_end else None
                            ),
                            "to_fiscal_period_end": (b.to_fiscal_period_end.isoformat() if b.to_fiscal_period_end else None),
                            "divisor_source_metric": b.divisor_source_metric,
                            "divisor_ratio": _num(b.divisor_ratio),
                            "detail": b.detail,
                        }
                        for b in per_share.breaks
                    ],
                    "note": (
                        "1株当たり指標は開示時点のまま(as-reported)で、株式分割をさかのぼって"
                        "調整していない。corporate_actions_known_from より前のCorporate Actionは"
                        "観測できておらず、無かったという意味ではない(UNKNOWN)。"
                    ),
                },
                "not_applicable_under_standard": not_applicable_families,
                "forecast_revisions": [
                    {
                        "metric_family": s.metric_family,
                        "target_fiscal_year_end": (s.target_fiscal_year_end.isoformat() if s.target_fiscal_year_end else None),
                        "accounting_standards": list(s.accounting_standards),
                        "revision_count": s.revision_count,
                        "observation_count": s.observation_count,
                        "revisions": [
                            {
                                "published_at": r.published_at.isoformat() if r.published_at else None,
                                "disclosure_period_type": r.disclosure_period_type.value,
                                "value": _num(r.value),
                                "previous_value": _num(r.previous_value),
                                "direction": r.direction.value,
                                "change_ratio": _num(r.change_ratio),
                                "source_metric_type": r.source_metric_type,
                                "unknown_reason": r.unknown_reason.value if r.unknown_reason else None,
                            }
                            for r in s.revisions
                        ],
                    }
                    for s in forecasts
                ],
            }
        )

    correlation = assess_correlation(source=price_source, codes=codes, as_of=as_of, max_staleness_days=args.max_staleness_days)

    report = {
        "as_of": as_of.isoformat(),
        "price_retrieved_at": bars_result.retrieved_at.isoformat(),
        "fins_retrieved_at": fins_result.retrieved_at.isoformat(),
        "availability_semantics": semantics.value,
        "include_unknown_availability": args.include_unknown_availability,
        "trend_years": args.years,
        "position_value": args.position_value,
        "entries": entries,
        "correlation": [
            {
                "code_a": p.code_a,
                "code_b": p.code_b,
                "outcome": p.outcome.value,
                "correlation": p.correlation,
                "overlapping_returns": p.overlapping_returns,
                "max_interval_days": p.max_interval_days,
                "unknown_reason": p.unknown_reason,
            }
            for p in correlation.pairs
        ],
        "unavailable": {
            "metrics": [m for m in UNMAPPED_METRICS if m not in ("roe", "dividend_yield", "book_value_per_share", "pbr")],
            "reason": (
                "2026-11-24にnormalize.pyへのマッピングは完了している"
                "(provider_reported_roe / bps / shares_outstanding_period_end 等)。"
                "ここで出ないのはScreener側のOrchestrationが未実装のため。"
            ),
            "per_percentile": "2026-11-24に entries[].valuation_percentiles として実装済み",
        },
        "valuation_source": {
            "available": valuation_unavailable_reason is None,
            "unavailable_reason": valuation_unavailable_reason,
            "requested_codes": valuation_codes,
        },
        "earnings_date_source": {
            "available": earnings_unavailable_reason is None,
            "unavailable_reason": earnings_unavailable_reason,
        },
        "instrument_master": {
            "available": master_unavailable_reason is None,
            "unavailable_reason": master_unavailable_reason,
        },
        "warnings": {
            "liquidity": liquidity_warned,
            "correlation": [[p.code_a, p.code_b] for p in correlation.warned_pairs],
            "per_share_basis": per_share_warned,
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
