from core.watchlist import Watchlist, list_watchlists


def test_save_and_load_roundtrip(tmp_path):
    wl = Watchlist(name="my_list", codes=["7203", "AAPL"])
    wl.save(directory=tmp_path)

    loaded = Watchlist.load("my_list", directory=tmp_path)
    assert loaded.codes == ["7203", "AAPL"]


def test_load_missing_watchlist_raises(tmp_path):
    try:
        Watchlist.load("does_not_exist", directory=tmp_path)
        assert False, "FileNotFoundError should be raised"
    except FileNotFoundError:
        pass


def test_list_watchlists(tmp_path):
    Watchlist(name="a", codes=[]).save(directory=tmp_path)
    Watchlist(name="b", codes=[]).save(directory=tmp_path)
    assert list_watchlists(tmp_path) == ["a", "b"]
