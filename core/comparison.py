"""複数銘柄比較用のテーブル・正規化ロジック。"""

from __future__ import annotations

from core.models import StockSnapshot

COMPARISON_FIELDS = [
    ("per", "PER"),
    ("pbr", "PBR"),
    ("roe", "ROE"),
    ("dividend_yield", "配当利回り"),
    ("market_cap", "時価総額"),
]

# レーダーチャートでは「低いほど良い」指標(PER/PBR)を反転させないと直感に反するため
LOWER_IS_BETTER = {"per", "pbr"}

MAX_COMPARISON_TARGETS = 5
MIN_COMPARISON_TARGETS = 3


def build_comparison_table(snapshots: list[StockSnapshot]) -> list[dict]:
    """横並び比較用のレコードリストを返す(表示側でDataFrame化する想定)。"""
    rows = []
    for s in snapshots:
        row = {
            "銘柄コード": s.code,
            "銘柄名": s.name or "-",
            "取得日時": s.fetched_at.isoformat(sep=" ", timespec="minutes"),
        }
        for attr, label in COMPARISON_FIELDS:
            row[label] = getattr(s, attr)
        rows.append(row)
    return rows


def normalize_for_radar(snapshots: list[StockSnapshot]) -> dict[str, list[float]]:
    """レーダーチャート用に各指標を0〜1へ正規化する(銘柄群内でのmin-max正規化)。

    値が欠損している銘柄はその指標について0として扱う(グラフ上「データなし」を
    明示するため、表側では別途「取得不可」の注記を推奨する)。
    """
    series: dict[str, list[float]] = {}
    for attr, label in COMPARISON_FIELDS:
        raw = [getattr(s, attr) for s in snapshots]
        values = [v for v in raw if v is not None]
        if not values:
            series[label] = [0.0 for _ in snapshots]
            continue
        lo, hi = min(values), max(values)
        span = hi - lo

        def scale(v: float | None) -> float:
            if v is None:
                return 0.0
            if span == 0:
                return 1.0
            normalized = (v - lo) / span
            return 1 - normalized if attr in LOWER_IS_BETTER else normalized

        series[label] = [scale(v) for v in raw]
    return series
