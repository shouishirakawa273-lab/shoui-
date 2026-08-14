"""キャッシュ・実績データ取得・異常値検証を束ねる高レベルAPI。

UI層(Streamlit)はこのモジュールの関数だけを呼び出せばよく、
キャッシュの有無やバリデーションの詳細を意識しなくてよいようにする。
"""

from __future__ import annotations

from core.cache import Cache
from core.errors import ProviderError
from core.models import Market, StockSnapshot
from core.providers.market_data import fetch_snapshot, infer_market
from core.validation import validate_snapshot


def load_snapshot(
    code: str,
    market: Market | None = None,
    cache: Cache | None = None,
    force_refresh: bool = False,
) -> StockSnapshot:
    """キャッシュを優先しつつ銘柄スナップショットを取得し、異常値検証を行う。

    Raises:
        ProviderError: キャッシュに無く、かつ新規取得にも失敗した場合。
    """
    resolved_market = market or infer_market(code)
    cache = cache or Cache()

    snapshot = None if force_refresh else cache.get_snapshot(code, resolved_market)
    if snapshot is None:
        snapshot = fetch_snapshot(code, resolved_market)
        cache.set_snapshot(snapshot)

    snapshot.warnings = validate_snapshot(snapshot)
    return snapshot


def load_snapshots(
    codes: list[str],
    cache: Cache | None = None,
    force_refresh: bool = False,
) -> tuple[list[StockSnapshot], dict[str, str]]:
    """複数銘柄をまとめて取得する。失敗した銘柄はコード -> エラー理由の辞書で返す。"""
    cache = cache or Cache()
    snapshots: list[StockSnapshot] = []
    errors: dict[str, str] = {}
    for code in codes:
        try:
            snapshots.append(load_snapshot(code, cache=cache, force_refresh=force_refresh))
        except ProviderError as exc:
            errors[code] = str(exc)
    return snapshots, errors
