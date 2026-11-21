"""保有候補の流動性・相関を警告する(Step 1、読み取り専用)。

銘柄コードと想定ポジション額を渡すと、J-Quantsから日次Barを取得し、
`lib/pretrade_risk` で流動性と相関を評価してJSONを出力する。

読み取り専用。発注・ファイル書き込み・Store作成は一切行わない。最終的な
BUY/HOLD/SELL判断は必ず人間が行う。

PIT安全性: `--as-of` までのBarのみを使う。J-Quantsからの取得期間も `--as-of`
までに限定し、その後 `AsOfAdjustedPriceHistory` がCorporate Action調整を
as_of基準で行う(未来の分割は構造的に混入しない)。

APIキーは環境変数 `JQUANTS_API_KEY`(リポジトリルートの `.env`)からのみ読む。
本スクリプトはキーを出力しない。

実行例:
    python scripts/pretrade_check.py --codes 3283 2979 8967 --position-value 100000
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.backtest.price_history import AsOfAdjustedPriceHistory  # noqa: E402
from lib.data_sources.convert import (  # noqa: E402
    detect_corporate_action_events_from_equity_bars,
    equity_bars_payload_to_raw_bars,
)
from lib.data_sources.jquants import JQuantsAdapter  # noqa: E402
from lib.errors import DataSourceError  # noqa: E402
from lib.pretrade_risk import assess_correlation, assess_liquidity  # noqa: E402
from lib.pretrade_risk.correlation import DEFAULT_MIN_OVERLAP, DEFAULT_THRESHOLD  # noqa: E402
from lib.pretrade_risk.correlation import DEFAULT_WINDOW_SESSIONS as CORRELATION_WINDOW  # noqa: E402
from lib.pretrade_risk.liquidity import DEFAULT_MIN_KNOWN_RATIO, DEFAULT_THRESHOLD_DAYS  # noqa: E402
from lib.pretrade_risk.liquidity import DEFAULT_WINDOW_SESSIONS as LIQUIDITY_WINDOW  # noqa: E402

# 暦日。250営業日ぶんのBarを確実に含めるための取得開始マージン。
FETCH_MARGIN_DAYS = 600


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--codes", nargs="+", required=True, help="銘柄コード(スペース区切り)")
    parser.add_argument("--position-value", type=float, required=True, help="1銘柄あたりの想定ポジション額(円)")
    parser.add_argument("--as-of", type=date.fromisoformat, default=None, help="判定時点(YYYY-MM-DD、既定は今日)")
    parser.add_argument("--liquidity-window", type=int, default=LIQUIDITY_WINDOW)
    parser.add_argument("--liquidity-threshold-days", type=float, default=DEFAULT_THRESHOLD_DAYS)
    parser.add_argument("--min-known-ratio", type=float, default=DEFAULT_MIN_KNOWN_RATIO)
    parser.add_argument("--correlation-window", type=int, default=CORRELATION_WINDOW)
    parser.add_argument("--correlation-threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--min-overlap", type=int, default=DEFAULT_MIN_OVERLAP)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    codes = list(dict.fromkeys(args.codes))
    as_of_date = args.as_of or datetime.now(UTC).date()
    as_of = datetime(as_of_date.year, as_of_date.month, as_of_date.day, 23, 59, tzinfo=UTC)

    adapter = JQuantsAdapter()
    try:
        fetched = adapter.fetch_equity_bars(
            codes=codes,
            start_date=as_of_date - timedelta(days=FETCH_MARGIN_DAYS),
            end_date=as_of_date,
        )
    except DataSourceError as exc:
        # 認証・疎通の失敗は想定内。キーは出力しない。
        print(json.dumps({"status": "DATA_SOURCE_UNAVAILABLE", "detail": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    raw_bars = equity_bars_payload_to_raw_bars(fetched.payload)
    events = detect_corporate_action_events_from_equity_bars(fetched.payload)

    raw_by_code: dict[str, list] = {code: [] for code in codes}
    for bar in raw_bars:
        raw_by_code.setdefault(bar.code, []).append(bar)
    events_by_code: dict[str, list] = {code: [] for code in codes}
    for event in events:
        events_by_code.setdefault(event.code, []).append(event)

    source = AsOfAdjustedPriceHistory(raw_by_code, events_by_code)

    liquidity = [
        assess_liquidity(
            source=source,
            code=code,
            position_value=args.position_value,
            as_of=as_of,
            window_sessions=args.liquidity_window,
            threshold_days=args.liquidity_threshold_days,
            min_known_ratio=args.min_known_ratio,
        )
        for code in codes
    ]
    correlation = assess_correlation(
        source=source,
        codes=codes,
        as_of=as_of,
        window_sessions=args.correlation_window,
        threshold=args.correlation_threshold,
        min_overlap=args.min_overlap,
    )

    report = {
        "as_of": as_of.isoformat(),
        "retrieved_at": fetched.retrieved_at.isoformat(),
        "data_period": fetched.data_period,
        "position_value": args.position_value,
        "liquidity": [
            {
                "code": item.code,
                "outcome": item.outcome.value,
                "sessions_observed": item.sessions_observed,
                "sessions_known": item.sessions_known,
                "sessions_unknown": item.sessions_unknown,
                "average_daily_turnover": item.average_daily_turnover,
                "days_to_liquidate": item.days_to_liquidate,
                "threshold_days": item.threshold_days,
                "unknown_reason": item.unknown_reason,
            }
            for item in liquidity
        ],
        "correlation": [
            {
                "code_a": pair.code_a,
                "code_b": pair.code_b,
                "outcome": pair.outcome.value,
                "correlation": pair.correlation,
                "overlapping_returns": pair.overlapping_returns,
                "threshold": pair.threshold,
                "unknown_reason": pair.unknown_reason,
            }
            for pair in correlation.pairs
        ],
        "warnings": {
            "liquidity": [item.code for item in liquidity if item.outcome.value == "WARN"],
            "correlation": [[p.code_a, p.code_b] for p in correlation.warned_pairs],
        },
        "unknown": {
            "liquidity": [item.code for item in liquidity if item.outcome.value == "UNKNOWN"],
            "correlation": [[p.code_a, p.code_b] for p in correlation.unknown_pairs],
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
