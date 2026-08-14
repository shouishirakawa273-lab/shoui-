"""ローカル環境でデータソースへの疎通確認を行うスクリプト。

クラウドのセッションからは外部APIへ接続できないため、このスクリプトは
必ずあなたのローカルPC上で(.envを設定した上で)実行してください。

使い方:
    python scripts/check_provider.py market 7203 AAPL
    python scripts/check_provider.py forecast 7203 AAPL
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

from core.errors import ProviderError  # noqa: E402
from core.forecast import get_forecast  # noqa: E402
from core.providers.market_data import fetch_snapshot, infer_market  # noqa: E402

load_dotenv()


def check_market_data(codes: list[str]) -> None:
    for code in codes:
        market = infer_market(code)
        print(f"\n=== {code} ({market.value}) : market_data ===")
        try:
            snapshot = fetch_snapshot(code, market)
        except ProviderError as exc:
            print(f"[NG] {exc}")
            continue
        print(
            f"[OK] price={snapshot.price} {snapshot.currency}, PER={snapshot.per}, PBR={snapshot.pbr}, "
            f"ROE={snapshot.roe}, 配当利回り={snapshot.dividend_yield}, 時価総額={snapshot.market_cap}"
        )
        print(f"     52週高値={snapshot.week52_high} / 52週安値={snapshot.week52_low}")
        print(f"     セクター={snapshot.sector} / 業種={snapshot.industry}")
        print(f"     売上高={snapshot.revenue_ttm} / 営業利益={snapshot.operating_income_ttm} / 純利益={snapshot.net_income_ttm}")
        print(f"     取得日時={snapshot.fetched_at}")


def check_forecast(codes: list[str]) -> None:
    for code in codes:
        market = infer_market(code)
        print(f"\n=== {code} ({market.value}) : forecast ===")
        try:
            forecast = get_forecast(code, market)
        except ProviderError as exc:
            print(f"[NG] {exc}")
            continue
        for v in forecast.values:
            if v.available and v.label is not None:
                print(f"[OK] {v.metric} = {v.value} ({v.label.value}, 出典: {v.source}, 更新日: {v.as_of})")
            else:
                print(f"[N/A] {v.metric}: {v.as_of or v.source}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    mode, *codes = sys.argv[1:]
    if mode == "market":
        check_market_data(codes)
    elif mode == "forecast":
        check_forecast(codes)
    else:
        print(f"未知のモードです: {mode} (market または forecast を指定してください)")
        sys.exit(1)
