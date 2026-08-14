from datetime import timedelta

from core.cache import Cache
from core.models import Market, StockSnapshot


def _snapshot() -> StockSnapshot:
    return StockSnapshot(code="7203", market=Market.JP, price=2500, per=15)


def test_set_and_get_snapshot_roundtrip(tmp_path):
    cache = Cache(db_path=tmp_path / "test.sqlite3")
    snapshot = _snapshot()
    cache.set_snapshot(snapshot)

    cached = cache.get_snapshot("7203", Market.JP)
    assert cached is not None
    assert cached.price == 2500
    assert cached.per == 15


def test_get_snapshot_returns_none_when_expired(tmp_path):
    cache = Cache(db_path=tmp_path / "test.sqlite3", ttl=timedelta(seconds=-1))
    cache.set_snapshot(_snapshot())
    assert cache.get_snapshot("7203", Market.JP) is None


def test_get_snapshot_returns_none_when_missing(tmp_path):
    cache = Cache(db_path=tmp_path / "test.sqlite3")
    assert cache.get_snapshot("9999", Market.JP) is None
