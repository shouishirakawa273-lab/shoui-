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

    `retrieved_at`は「Research Labがこのデータを取得した日時」であり、
    `lib.point_in_time.PointInTimeRecord.available_at`(「市場参加者が当時実際に
    参照可能になった日時」)とは別物である。両者を混同すると、例えば数年前の
    株価データを今日取得した場合に`available_at`まで「今日」だと誤認し、
    過去のバックテストで一切そのデータを使えなくなる(=Look-ahead防止のつもりが
    過度に保守的になる)、あるいは逆に混同の仕方によっては未来情報の混入を見逃す、
    といった誤りにつながる。`available_at`は常に市場の営業時間(`lib/market_calendar.py`)
    から導出し、`retrieved_at`から導出しないこと
    (`13_tests/test_available_at_vs_retrieved_at.py`で確認する)。
    """

    source: str
    endpoint: str
    request_parameters: dict[str, Any]
    retrieved_at: datetime
    data_period: str
    response_schema_version: str
    payload: Any


class DataSourceAdapter(Protocol):
    """日次株価データソースが実装すべきInterface。

    Phase3Aで`fetch_index_prices` / `fetch_listed_info`を追加した(TOPIX・Universe
    マスタデータのため)。Fundamental Data(決算等)はまだこのInterfaceに含めない。
    """

    def fetch_daily_quotes(self, *, codes: Sequence[str], start_date: date, end_date: date) -> RawFetchResult:
        """指定銘柄群の日次OHLCV(未調整)を取得する。"""
        ...

    def fetch_trading_calendar(self, *, start_date: date, end_date: date) -> RawFetchResult:
        """指定期間の取引カレンダー(取引日/休場日)を取得する。"""
        ...

    def fetch_index_prices(self, *, index_code: str, start_date: date, end_date: date) -> RawFetchResult:
        """指定インデックス(例: TOPIX)の日次価格を取得する。"""
        ...

    def fetch_listed_info(self, *, as_of: date | None = None) -> RawFetchResult:
        """銘柄マスタ(上場情報)を取得する。as_ofに対応しないSourceは現在情報を返す。"""
        ...
