"""保有候補の流動性・相関を警告する(Step 1、読み取り専用)。

銘柄コードと想定ポジション額を渡すと、J-Quantsから日次Barを取得し、
`lib/pretrade_risk` で流動性と相関を評価してJSONを出力する。

読み取り専用。発注・ファイル書き込み・Store作成は一切行わない。最終的な
BUY/HOLD/SELL判断は必ず人間が行う。

PIT安全性:

- `--as-of` を省略した場合の判定時点は「いま(JST)」である。暦日の終わりを
  仮定しない。`lib/pretrade_risk/window.py` が大引け未到来のセッションを除外
  するので、場中に実行しても当日の未完セッションは使われない。
- `--as-of` に日付を与えた場合はその日の大引け(`session_close_at`)を判定時点と
  する。未来日は拒否する。
- 取得期間は `as_of` までに限定し、`AsOfAdjustedPriceHistory` がCorporate Action
  調整を `as_of` 基準で行う(未来の分割は構造的に混入しない)。

APIキーは環境変数 `JQUANTS_API_KEY`(リポジトリルートの `.env`)からのみ読む。
本スクリプトはキーを出力しない。

実行例:
    python scripts/pretrade_check.py --codes 3283 2979 8967 --position-value 1000000
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.dont_write_bytecode = True
_LAB_DIR = Path(__file__).resolve().parents[1]
_REPO_ROOT = _LAB_DIR.parent
sys.path.insert(0, str(_LAB_DIR))

from dotenv import load_dotenv  # noqa: E402
from lib.backtest.price_history import AsOfAdjustedPriceHistory  # noqa: E402
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
from lib.market_calendar import JST, session_close_at  # noqa: E402
from lib.pretrade_risk import assess_correlation, assess_liquidity  # noqa: E402
from lib.pretrade_risk.correlation import DEFAULT_MIN_OVERLAP, DEFAULT_THRESHOLD  # noqa: E402
from lib.pretrade_risk.correlation import DEFAULT_WINDOW_SESSIONS as CORRELATION_WINDOW  # noqa: E402
from lib.pretrade_risk.liquidity import (  # noqa: E402
    DEFAULT_MAX_STALENESS_DAYS,
    DEFAULT_MIN_KNOWN_RATIO,
    DEFAULT_THRESHOLD_DAYS,
)
from lib.pretrade_risk.liquidity import DEFAULT_WINDOW_SESSIONS as LIQUIDITY_WINDOW  # noqa: E402

# 暦日。250営業日ぶんのBarを確実に含めるための取得開始マージン。
FETCH_MARGIN_DAYS = 600


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--codes", nargs="+", required=True, help="銘柄コード(スペース区切り)")
    parser.add_argument("--position-value", type=float, required=True, help="1銘柄あたりの想定ポジション額(円)")
    parser.add_argument("--as-of", type=date.fromisoformat, default=None, help="判定日(YYYY-MM-DD)。既定はいま(JST)")
    parser.add_argument("--liquidity-window", type=int, default=LIQUIDITY_WINDOW)
    parser.add_argument("--liquidity-threshold-days", type=float, default=DEFAULT_THRESHOLD_DAYS)
    parser.add_argument("--min-known-ratio", type=float, default=DEFAULT_MIN_KNOWN_RATIO)
    parser.add_argument("--correlation-window", type=int, default=CORRELATION_WINDOW)
    parser.add_argument("--correlation-threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--min-overlap", type=int, default=DEFAULT_MIN_OVERLAP)
    parser.add_argument("--max-staleness-days", type=int, default=DEFAULT_MAX_STALENESS_DAYS)
    return parser.parse_args(argv)


def _fail(status: str, detail: str) -> int:
    print(json.dumps({"status": status, "detail": detail}, ensure_ascii=False), file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    # 実行ディレクトリに依存しないよう、リポジトリルートの.envを明示指定する。
    load_dotenv(_REPO_ROOT / ".env")

    try:
        normalized = [normalize_provider_code_to_internal(code) for code in args.codes]
    except TickerCodeNormalizationError as exc:
        return _fail("INVALID_CODE", str(exc))
    codes = list(dict.fromkeys(normalized))

    now = datetime.now(JST)
    as_of = session_close_at(args.as_of) if args.as_of is not None else now
    if as_of > now:
        return _fail("AS_OF_IN_FUTURE", f"as_of {as_of.isoformat()} is after now {now.isoformat()}")

    adapter = JQuantsAdapter()
    try:
        fetched = adapter.fetch_equity_bars(
            codes=codes,
            start_date=as_of.date() - timedelta(days=FETCH_MARGIN_DAYS),
            end_date=as_of.date(),
        )
    except DataSourceError as exc:
        # 認証・疎通の失敗は想定内。キーは出力しない。
        return _fail("DATA_SOURCE_UNAVAILABLE", str(exc))

    if as_of > fetched.retrieved_at:
        return _fail(
            "AS_OF_AFTER_RETRIEVAL",
            f"as_of {as_of.isoformat()} is after retrieved_at {fetched.retrieved_at.isoformat()}",
        )

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
            max_staleness_days=args.max_staleness_days,
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
        max_staleness_days=args.max_staleness_days,
    )

    report = {
        "as_of": as_of.isoformat(),
        "retrieved_at": fetched.retrieved_at.isoformat(),
        # 要求した期間であって、実際に返ってきた範囲ではない。観測範囲は
        # liquidity[].first_session / last_session を見ること。
        "requested_data_period": fetched.data_period,
        "position_value": args.position_value,
        "liquidity": [
            {
                "code": item.code,
                "outcome": item.outcome.value,
                "sessions_observed": item.sessions_observed,
                "sessions_known": item.sessions_known,
                "sessions_unknown": item.sessions_unknown,
                "duplicate_sessions_dropped": item.duplicate_sessions_dropped,
                "first_session": item.first_session.isoformat() if item.first_session else None,
                "last_session": item.last_session.isoformat() if item.last_session else None,
                "staleness_days": item.staleness_days,
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
                "max_interval_days": pair.max_interval_days,
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
