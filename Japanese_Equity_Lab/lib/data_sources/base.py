"""外部データソース(J-Quants等)への依存をBacktest Engineから切り離すためのInterface。

Backtest Engineや変換ロジックは`DataSourceAdapter`だけに依存し、特定のサービス
(J-Quants等)固有のコードを直接書かない。将来別のデータソースへ差し替える場合は
新しいAdapterを実装するだけでよい。

`fetch_*`はAPIレスポンスをそのまま(可能な限り未加工で)`RawFetchResult`として返す。
schemaへの変換は`lib/data_sources/convert.py`が別途行う(取得と変換の責務を分離する)。

**Phase3A.1でJ-Quants API V2へ全面移行した**(DECISIONS.md D0031以降)。V1の
`/prices/daily_quotes` 等のEndpoint名・Field名を前提としたコードはこのリポジトリから
削除済み。V2のEndpoint一覧・Field名はユーザーが本セッション内で明示した仕様を
Canonical Specificationとして使用している(このセッションはJ-Quantsの公式ドキュメントへ
疎通できず、独自に検証できていない。DECISIONS.md D0031参照)。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class RawFetchResult:
    """1回のAPI呼び出しの結果。01_data/raw/へのSnapshot保存に必要な情報を全て含む。

    request_parametersに認証情報(APIキー等)を含めてはならない
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

    `pagination_key`: V2 APIは1リクエストで返しきれない場合に`pagination_key`を
    返し、次リクエストで引き継ぐページネーションを行う。`payload`には全ページを
    結合した最終結果のみを保持し、途中経過のpagination_keyはSnapshotに残さない
    (Adapter内部で完結させる)。
    """

    source: str
    endpoint: str
    request_parameters: dict[str, Any]
    retrieved_at: datetime
    data_period: str
    response_schema_version: str
    payload: Any


class DataSourceAdapter(Protocol):
    """日次株価データソースが実装すべきInterface(J-Quants API V2ベース)。

    Phase3A.1でV1から全面移行した。Fundamental Data(決算等)はまだこのInterfaceに
    含めない。

    **Capability自己申告について**: 契約プラン等によりどのDatasetが利用可能かの
    自己申告は、このProtocol自体では持たない(旧`DataSourceCapabilities`/
    `LIGHT_PLAN_ASSUMED`はJQS-STD-01Aで削除、DECISIONS.md参照)。実装は
    `lib.sources.providers.MarketDataProvider`(`capabilities -> ProviderCapabilities`、
    Phase3D/D0040の共通Capability-based Design)を構造的に満たすことでこれを表現する
    (`13_tests/test_source_providers.py`で確認)。実際に呼び出し可能かどうかは
    事前判定せず、常にAPI呼び出し自体の成否(`DataSourceError`)で判断する
    (RESEARCH_RULES.md、他Providerへのsilent fallback禁止)。
    """

    def fetch_equity_bars(self, *, codes: Sequence[str], start_date: date, end_date: date) -> RawFetchResult:
        """``GET /v2/equities/bars/daily``: 指定銘柄群の日次Bar(Raw + Adjusted両方)を取得する。"""
        ...

    def fetch_trading_calendar(self, *, start_date: date, end_date: date) -> RawFetchResult:
        """``GET /v2/markets/calendar``: 指定期間の取引カレンダー(取引日/休場日)を取得する。"""
        ...

    def fetch_topix_bars(self, *, start_date: date, end_date: date) -> RawFetchResult:
        """``GET /v2/indices/bars/daily/topix``: TOPIX専用Endpointから日次価格を取得する。"""
        ...

    def fetch_general_index_bars(self, *, index_code: str, start_date: date, end_date: date) -> RawFetchResult:
        """``GET /v2/indices/bars/daily``: TOPIX以外の一般指数(業種指数等)を取得する場合のみ使用する。

        既定のPipelineでは呼び出さない(Benchmarkは`fetch_topix_bars`を使う)。
        """
        ...

    def fetch_equities_master(self, *, as_of: date | None = None) -> RawFetchResult:
        """``GET /v2/equities/master``: 銘柄マスタ(上場情報)を取得する。

        as_ofに対応する場合はその時点のMaster Snapshotを、対応しないSourceは
        現在情報を返す。
        """
        ...
