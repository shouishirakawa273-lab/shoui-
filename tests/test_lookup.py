from unittest.mock import patch

from core.cache import Cache
from core.errors import ProviderError
from core.lookup import load_snapshot, load_snapshots
from core.models import Market, StockSnapshot


def _fake_snapshot(code):
    return StockSnapshot(code=code, market=Market.JP, price=100, per=9999)  # PERは異常値


@patch("core.lookup.fetch_snapshot")
def test_load_snapshot_fetches_and_validates(mock_fetch, tmp_path):
    mock_fetch.return_value = _fake_snapshot("7203")
    cache = Cache(db_path=tmp_path / "t.sqlite3")

    snapshot = load_snapshot("7203", market=Market.JP, cache=cache)

    assert snapshot.per == 9999
    assert any(w.field == "per" for w in snapshot.warnings)
    mock_fetch.assert_called_once()


@patch("core.lookup.fetch_snapshot")
def test_load_snapshot_uses_cache_on_second_call(mock_fetch, tmp_path):
    mock_fetch.return_value = _fake_snapshot("7203")
    cache = Cache(db_path=tmp_path / "t.sqlite3")

    load_snapshot("7203", market=Market.JP, cache=cache)
    load_snapshot("7203", market=Market.JP, cache=cache)

    mock_fetch.assert_called_once()  # 2回目はキャッシュヒットするので再取得しない


@patch("core.lookup.fetch_snapshot")
def test_load_snapshots_collects_errors_without_raising(mock_fetch, tmp_path):
    def side_effect(code, market):
        if code == "BAD":
            raise ProviderError("not found")
        return _fake_snapshot(code)

    mock_fetch.side_effect = side_effect
    cache = Cache(db_path=tmp_path / "t.sqlite3")

    snapshots, errors = load_snapshots(["7203", "BAD"], cache=cache)

    assert [s.code for s in snapshots] == ["7203"]
    assert errors == {"BAD": "not found"}
