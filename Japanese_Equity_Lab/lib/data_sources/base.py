"""外部データソース(J-Quants等)への依存をBacktest Engineから切り離すためのInterface。

Backtest Engineや変換ロジックは`DataSourceAdapter`だけに依存し、特定のサービス
(J-Quants等)固有のコードを直接書かない。将来別のデータソースへ差し替える場合は
新しいAdapterを実装するだけでよい。

`fetch_*`はAPIレスポンスをそのまま(可能な限り未加工で)`RawFetchResult`として返す。
schemaへの変換は`lib/data_sources/convert.py`が別途行う(取得と変換の責務を分離する)。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class RawFetchResult:
    """1回のAPI呼び出しの結果。01_data/raw/へのSnapshot保存に必要な情報を全て含む。

    request_parametersに認証情報(トークン・APIキー等)を含めてはならない
    (Snapshot manifestとしてそのまま保存されるため)。
    """

    source: str
    endpoint: str
    request_parameters: dict[str, Any]
    retrieved_at: datetime
    data_period: str
    response_schema_version: str
    payload: Any


class DataSourceAdapter(Protocol):
    """日次株価データソースが実装すべきInterface。"""

    def fetch_daily_quotes(self, *, codes: Sequence[str], start_date: date, end_date: date) -> RawFetchResult:
        """指定銘柄群の日次OHLCV(未調整)を取得する。"""
        ...

    def fetch_trading_calendar(self, *, start_date: date, end_date: date) -> RawFetchResult:
        """指定期間の取引カレンダー(取引日/休場日)を取得する。"""
        ...
