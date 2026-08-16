from __future__ import annotations

from lib.reproducibility import current_code_commit, dataset_hash_from_snapshots, hash_json_safe


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
