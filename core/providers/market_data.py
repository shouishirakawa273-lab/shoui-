"""実績データ(株価・PER/PBR等)の取得。

yfinance を利用する。APIキー不要で日本株(証券コード)・米国株(ティッカー)の
両方をカバーできるためこのソースを選んだ。ネットワーク不通・銘柄が存在しない
場合は例外を投げず、理由付きの `ProviderError` を送出して呼び出し側で
明示的にハンドリングする(無言で落とさない)。
"""

from __future__ import annotations

import logging
from datetime import datetime

from core.errors import ProviderError
from core.models import Market, StockSnapshot

logger = logging.getLogger(__name__)


def normalize_symbol(code: str, market: Market) -> str:
    """内部コードを yfinance が要求するシンボル形式に変換する。

    日本株は証券コードに ``.T`` を付与する(例: 7203 -> 7203.T)。
    すでにサフィックスが付いている場合はそのまま扱う。
    """
    code = code.strip().upper()
    if market == Market.JP and not code.endswith(".T"):
        return f"{code}.T"
    return code


def infer_market(code: str) -> Market:
    """入力コードから市場を推定する。4桁数字(+末尾アルファベット可)は日本株。"""
    stripped = code.strip().upper().removesuffix(".T")
    if stripped[:4].isdigit() and len(stripped) <= 5:
        return Market.JP
    return Market.US


def _fetch_latest_financials(ticker) -> tuple[float | None, float | None, float | None]:
    """直近会計年度の損益計算書から売上高・営業利益・純利益を取得する。

    ``ticker.info`` の要約フィールドより ``financials`` (年次損益計算書)の方が
    実績値として正確なため、取得できる場合はこちらを優先する。取得に失敗しても
    メインの取得処理は止めず、(None, None, None) を返して呼び出し側にフォール
    バックさせる。
    """
    try:
        financials = ticker.financials
        if financials is None or financials.empty:
            return None, None, None
        latest_col = financials.columns[0]

        def _get(row_name: str) -> float | None:
            if row_name in financials.index:
                value = financials.loc[row_name, latest_col]
                return None if value != value else float(value)  # NaN check
            return None

        return _get("Total Revenue"), _get("Operating Income"), _get("Net Income")
    except Exception as exc:  # 財務諸表取得の失敗は致命的ではないためログのみ
        logger.warning("financials fetch failed: %s", exc)
        return None, None, None


def fetch_snapshot(code: str, market: Market | None = None) -> StockSnapshot:
    """指定銘柄の実績スナップショットを取得する。

    Raises:
        ProviderError: 銘柄が存在しない、ネットワークエラー等で取得できない場合。
    """
    try:
        import yfinance as yf
    except ImportError as exc:  # pragma: no cover - 依存未インストール時のみ
        raise ProviderError("yfinance がインストールされていません") from exc

    resolved_market = market or infer_market(code)
    symbol = normalize_symbol(code, resolved_market)

    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
    except Exception as exc:  # yfinance/requests 由来の例外を統一的に扱う
        raise ProviderError(f"{symbol} の取得中にエラーが発生しました: {exc}") from exc

    if not info or info.get("regularMarketPrice") is None and info.get("currentPrice") is None:
        raise ProviderError(
            f"{symbol} のデータが見つかりません(銘柄コードが存在しないか、データソース側で提供されていない可能性があります)"
        )

    price = info.get("currentPrice") or info.get("regularMarketPrice")

    # yfinanceの dividendYield はパーセント値そのもの(3.35 = 3.35%)で返るため常に/100する。
    # dividendRate(1株配当額)÷price との検算で確認済み(2026-08時点、7203/AAPL)。
    dividend_yield = info.get("dividendYield")
    if dividend_yield is not None:
        dividend_yield = dividend_yield / 100

    # yfinanceの returnOnEquity は既に比率で返るため変換不要。
    # 自社株買いの影響でROEが100%(比率1.0)を超える銘柄(AAPL等)があるため、
    # 「1より大きければ%表記とみなして/100する」ような magnitude 依存の補正はしないこと。
    roe = info.get("returnOnEquity")

    revenue, operating_income, net_income = _fetch_latest_financials(ticker)

    snapshot = StockSnapshot(
        code=code,
        market=resolved_market,
        name=info.get("longName") or info.get("shortName"),
        currency=info.get("currency"),
        price=price,
        per=info.get("trailingPE"),
        pbr=info.get("priceToBook"),
        roe=roe,
        dividend_yield=dividend_yield,
        market_cap=info.get("marketCap"),
        week52_high=info.get("fiftyTwoWeekHigh"),
        week52_low=info.get("fiftyTwoWeekLow"),
        sector=info.get("sector"),
        industry=info.get("industry"),
        revenue_ttm=revenue if revenue is not None else info.get("totalRevenue"),
        operating_income_ttm=operating_income,
        net_income_ttm=net_income if net_income is not None else info.get("netIncomeToCommon"),
        fetched_at=datetime.now(),
        source="yfinance",
    )
    logger.info("fetched snapshot for %s at %s", symbol, snapshot.fetched_at)
    return snapshot
