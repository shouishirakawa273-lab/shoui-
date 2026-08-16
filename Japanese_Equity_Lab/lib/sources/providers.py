"""Source Adapter Interface: J-Quants専用実装へ研究所を依存させないためのProtocol群。

Capability-based Design(D0040)を優先する: 全Sourceを1つの巨大Interfaceへ詰め込まず、
データの形が本質的に異なるSource種別ごとに小さなProtocolを分け、各Providerは
`capabilities`で自分が何を提供できるかを自己申告する。Interface Explosionを避けるため、
形が似ているSource(例: EDINET/TDnet/Company IRはいずれも「開示文書」という共通の形)は
1つのProtocol(`DisclosureProvider`)へまとめ、`ProviderCapabilities.provider_name`等で
個別Sourceを区別する。

**このモジュールは実際の外部APIへ接続しない。** Protocol定義のみを提供する
(具体的な接続実装はPhase3D以降、各Sourceの公式仕様を確認した上で行う)。

**既存`lib.data_sources.base.DataSourceAdapter`(J-Quants V2向け、Phase3A.1〜)との
互換性**: `MarketDataProvider`は`DataSourceAdapter`と同じメソッド名・シグネチャで
設計してあり、既存の`JQuantsAdapter`/`FixtureDataSourceAdapter`/`LocalSnapshotAdapter`は
このファイルを一切変更しなくても構造的に`MarketDataProvider`を満たす
(`13_tests/test_source_providers.py`の互換性テストで確認する)。既存Adapterのコード自体は
変更しない。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol, runtime_checkable

from lib.data_sources.base import RawFetchResult
from lib.sources.catalog import DataCapability, SourceAuthorityClass


@dataclass(frozen=True)
class ProviderCapabilities:
    """Providerが自己申告する提供可能Capability(D0040)。

    契約プラン等により実際に呼び出せるかどうかまでは保証しない
    (`lib.data_sources.base.DataSourceCapabilities`と同様、事前ブロック用途には使わない。
    実際の可否は呼び出し自体の成否で判断する)。
    """

    provider_name: str
    capabilities: frozenset[DataCapability]
    authority_class: SourceAuthorityClass
    notes: str = ""


@runtime_checkable
class SourceProvider(Protocol):
    """全Providerに共通する最小限のInterface。"""

    @property
    def capabilities(self) -> ProviderCapabilities: ...


@runtime_checkable
class MarketDataProvider(SourceProvider, Protocol):
    """株価・指数・取引カレンダー・銘柄マスタ(J-Quants等)。

    既存`lib.data_sources.base.DataSourceAdapter`と同形状(互換性のため)。
    """

    def fetch_equity_bars(self, *, codes: Sequence[str], start_date: date, end_date: date) -> RawFetchResult: ...
    def fetch_trading_calendar(self, *, start_date: date, end_date: date) -> RawFetchResult: ...
    def fetch_topix_bars(self, *, start_date: date, end_date: date) -> RawFetchResult: ...
    def fetch_equities_master(self, *, as_of: date | None = None) -> RawFetchResult: ...


@runtime_checkable
class FundamentalDataProvider(SourceProvider, Protocol):
    """財務諸表・配当等(将来的なJ-Quants Financials/Dividend等)。"""

    def fetch_financial_statements(self, *, codes: Sequence[str], start_date: date, end_date: date) -> RawFetchResult: ...
    def fetch_dividends(self, *, codes: Sequence[str], start_date: date, end_date: date) -> RawFetchResult: ...


@runtime_checkable
class DisclosureProvider(SourceProvider, Protocol):
    """開示文書(EDINET/TDnet/Company IR等、共通して「文書1件」という形を持つ)。

    EDINET(有価証券報告書等)・TDnet(決算短信・業績予想修正・配当・自社株買い・M&A・
    適時開示)・Company IR(決算説明資料・中期経営計画等)は、いずれもこのProtocolを
    実装する別々のAdapterとして扱う(1つのAdapterに混在させない。
    `ProviderCapabilities.provider_name`で区別する)。
    """

    def fetch_disclosures(
        self, *, codes: Sequence[str], start_date: date, end_date: date, disclosure_types: Sequence[str] = ()
    ) -> RawFetchResult: ...


@runtime_checkable
class MacroDataProvider(SourceProvider, Protocol):
    """日本マクロ統計(BOJ/e-Stat/財務省/経産省/貿易統計等)。

    Revisionが起こりうる系列が多いため、呼び出し側は
    `lib.evidence.model.RevisionHistory`でVintage管理することを想定する。
    """

    def fetch_macro_series(self, *, series_id: str, start_date: date, end_date: date) -> RawFetchResult: ...


@runtime_checkable
class GlobalMarketDataProvider(SourceProvider, Protocol):
    """FX・金利・海外株価指数・Commodity等のCross Asset Data。"""

    def fetch_global_bars(self, *, instrument_id: str, start_date: date, end_date: date) -> RawFetchResult: ...


@runtime_checkable
class NewsProvider(SourceProvider, Protocol):
    """Japan News / Global Newsのニュース記事(メタデータ取得)。

    Newsを全件LLMへ投入する設計は禁止(RESEARCH_RULES.md参照)。このProviderは
    記事メタデータの取得までを担い、関連度評価・要約は別レイヤ
    (`lib.evidence.news`/将来のRetrieval)で行う。
    """

    def fetch_news(self, *, start_at: datetime, end_at: datetime) -> RawFetchResult: ...


@runtime_checkable
class ConsensusProvider(SourceProvider, Protocol):
    """Analyst Consensus / EPS Revision / Target Price等。

    実Providerは現時点(Phase3D)では未選定。Interfaceのみ用意する
    (`ProviderCapabilities`にEXPECTATIONSを申告するProviderは現時点で存在しない)。
    """

    def fetch_consensus(self, *, codes: Sequence[str], as_of: date) -> RawFetchResult: ...


@runtime_checkable
class IdeaSourceProvider(SourceProvider, Protocol):
    """X/YouTube/学術論文/手動入力等のIdea Source。

    **FACT Sourceではなく、IDEA/OPINION Sourceとして扱う**(RESEARCH_RULES.md参照)。
    既存`lib.schemas.idea.Idea`(`03_idea_inbox/`向け)と組み合わせて使うことを想定する。
    """

    def fetch_ideas(self, *, source_type: str, start_at: datetime, end_at: datetime) -> RawFetchResult: ...


ALL_PROVIDER_PROTOCOLS: tuple[type, ...] = (
    MarketDataProvider,
    FundamentalDataProvider,
    DisclosureProvider,
    MacroDataProvider,
    GlobalMarketDataProvider,
    NewsProvider,
    ConsensusProvider,
    IdeaSourceProvider,
)
