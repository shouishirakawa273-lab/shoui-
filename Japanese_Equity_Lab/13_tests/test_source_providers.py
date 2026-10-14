"""Phase3D(D0040): Capability-based Provider Protocolのテスト。

既存`JQuantsAdapter`/`FixtureDataSourceAdapter`を変更せずに、新設した
`MarketDataProvider` Protocolを構造的に満たすことを確認する(互換性)。
"""

from __future__ import annotations

from pathlib import Path

from lib.data_sources.fixture import FixtureDataSourceAdapter
from lib.data_sources.jquants import JQuantsAdapter
from lib.sources.providers import ALL_PROVIDER_PROTOCOLS, MarketDataProvider

_FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "synthetic_jquants_v2_bars.json"


def test_jquants_adapter_satisfies_market_data_provider_without_modification() -> None:
    adapter = JQuantsAdapter()
    assert isinstance(adapter, MarketDataProvider)


def test_fixture_adapter_satisfies_market_data_provider_without_modification() -> None:
    adapter = FixtureDataSourceAdapter(_FIXTURE_PATH)
    assert isinstance(adapter, MarketDataProvider)


def test_all_provider_protocols_declare_capabilities_property() -> None:
    """全Provider Protocolが共通の`capabilities`自己申告を持つ(Interface Explosion対策)。"""
    for protocol in ALL_PROVIDER_PROTOCOLS:
        assert hasattr(protocol, "capabilities")
