from __future__ import annotations

from pathlib import Path

from lib.reproducibility import current_code_commit, dataset_hash_from_snapshots, hash_json_safe, is_git_dirty


def test_hash_json_safe_is_order_independent() -> None:
    a = hash_json_safe({"b": 2, "a": 1})
    b = hash_json_safe({"a": 1, "b": 2})
    assert a == b


def test_hash_json_safe_differs_for_different_values() -> None:
    assert hash_json_safe({"a": 1}) != hash_json_safe({"a": 2})


def test_dataset_hash_from_snapshots_is_order_independent() -> None:
    assert dataset_hash_from_snapshots(["h1", "h2"]) == dataset_hash_from_snapshots(["h2", "h1"])


def test_current_code_commit_returns_str_or_none() -> None:
    # gitが無い/リポジトリ外でもNoneを返すだけでエラーにならないことを確認する。
    result = current_code_commit()
    assert result is None or isinstance(result, str)


def test_is_git_dirty_returns_bool_or_none() -> None:
    result = is_git_dirty()
    assert result is None or isinstance(result, bool)


def test_is_git_dirty_returns_none_outside_a_git_repository(tmp_path: Path) -> None:
    # gitリポジトリではないディレクトリでは判定不能としてNoneを返す(推測で埋めない)。
    assert is_git_dirty(cwd=str(tmp_path)) is None
    assert current_code_commit(cwd=str(tmp_path)) is None
