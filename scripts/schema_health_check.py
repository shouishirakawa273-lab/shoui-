"""CI(GitHub Actions)の定期実行から呼び出す健康診断スクリプト。

外部APIのレスポンス形式が変わっていないか、取得値が明らかに異常でないかを
チェックし、問題があれば非ゼロで終了する。J-Quants/FinnhubのAPIキーが
GitHub Secretsに設定されていない場合、該当チェックはスキップする
(スキップはCI失敗にはしない)。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.errors import ProviderError
from core.forecast import get_forecast
from core.models import Market
from core.providers.finnhub import FinnhubClient
from core.providers.jquants import JQuantsClient
from core.providers.market_data import fetch_snapshot
from core.validation import validate_snapshot

MARKET_DATA_CHECK_CODES = ["7203", "AAPL"]
REQUIRED_MARKET_FIELDS = ["price", "per", "pbr", "market_cap"]


def check_market_data() -> list[str]:
    """yfinanceのレスポンス形式・値の妥当性を確認する。問題点のリストを返す。"""
    problems: list[str] = []
    for code in MARKET_DATA_CHECK_CODES:
        try:
            snapshot = fetch_snapshot(code)
        except ProviderError as exc:
            problems.append(f"[market_data] {code}: 取得失敗 - {exc}")
            continue

        missing = [f for f in REQUIRED_MARKET_FIELDS if getattr(snapshot, f) is None]
        if missing:
            problems.append(
                f"[market_data] {code}: 想定フィールドが欠落しています({missing}) "
                "-> yfinanceのレスポンス形式が変わった可能性があります"
            )

        for w in validate_snapshot(snapshot):
            problems.append(f"[market_data] {code}: 異常値の可能性 - {w.message}")

    return problems


def check_forecast() -> list[str]:
    """J-Quants/Finnhubのレスポンス形式を確認する(APIキー未設定時はスキップ)。"""
    problems: list[str] = []

    jquants = JQuantsClient()
    if jquants.configured:
        try:
            forecast = get_forecast("7203", Market.JP, jquants=jquants)
            if not any(v.available for v in forecast.values):
                problems.append("[jquants] 7203: 全項目が取得不可でした -> レスポンス形式が変わった可能性があります")
        except ProviderError as exc:
            problems.append(f"[jquants] 7203: 取得失敗 - {exc}")
    else:
        print("[jquants] JQUANTS_REFRESH_TOKEN未設定のためスキップ")

    finnhub = FinnhubClient()
    if finnhub.configured:
        try:
            forecast = get_forecast("AAPL", Market.US, finnhub=finnhub)
            if not any(v.available for v in forecast.values):
                problems.append("[finnhub] AAPL: 全項目が取得不可でした -> レスポンス形式が変わった可能性があります")
        except ProviderError as exc:
            problems.append(f"[finnhub] AAPL: 取得失敗 - {exc}")
    else:
        print("[finnhub] FINNHUB_API_KEY未設定のためスキップ")

    return problems


def main() -> int:
    problems = check_market_data() + check_forecast()
    if problems:
        print("\n=== 健康診断で問題を検知しました ===")
        for p in problems:
            print(f"- {p}")
        return 1
    print("健康診断: 問題は検知されませんでした。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
