from __future__ import annotations

from pathlib import Path

from lib.reproducibility import (
    current_code_commit,
    dataset_hash_from_snapshots,
    hash_json_safe,
    is_git_dirty,
    source_code_state_hash,
)


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


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_source_code_state_hash_is_deterministic_for_same_content(tmp_path: Path) -> None:
    """同じSourceディレクトリ内容なら常に同じhashになる(commit状態に依存しない)。"""
    lib_dir = tmp_path / "lib"
    _write(lib_dir / "a.py", "x = 1\n")
    _write(lib_dir / "sub" / "b.py", "y = 2\n")

    first = source_code_state_hash([lib_dir], repo_root=tmp_path)
    second = source_code_state_hash([lib_dir], repo_root=tmp_path)
    assert first is not None
    assert first == second


def test_source_code_state_hash_changes_when_file_content_changes(tmp_path: Path) -> None:
    lib_dir = tmp_path / "lib"
    file_path = lib_dir / "a.py"
    _write(file_path, "x = 1\n")
    before = source_code_state_hash([lib_dir], repo_root=tmp_path)

    _write(file_path, "x = 2\n")
    after = source_code_state_hash([lib_dir], repo_root=tmp_path)
    assert before != after


def test_source_code_state_hash_ignores_non_python_files(tmp_path: Path) -> None:
    """.env等の非.pyファイルはSourceディレクトリ配下にあってもhash入力に含めない
    (Secretsをhash入力・Registryへ混入させないための構造的な除外、D0069)。"""
    lib_dir = tmp_path / "lib"
    _write(lib_dir / "a.py", "x = 1\n")
    baseline = source_code_state_hash([lib_dir], repo_root=tmp_path)

    _write(lib_dir / ".env", "SECRET_API_KEY=super-secret-value\n")
    after_env_added = source_code_state_hash([lib_dir], repo_root=tmp_path)
    assert baseline == after_env_added


def test_source_code_state_hash_is_not_contaminated_by_output_directories(tmp_path: Path) -> None:
    """呼び出し側がlib/以外のディレクトリ(06_backtests/等の生成物置き場)を対象パスに
    含めない限り、RunがRegistry/Reportを書き出してもhashは変化しない
    (git_dirty==Trueで機械的にブロックしない設計の裏付け)。"""
    lib_dir = tmp_path / "lib"
    output_dir = tmp_path / "06_backtests"
    _write(lib_dir / "a.py", "x = 1\n")
    before = source_code_state_hash([lib_dir], repo_root=tmp_path)

    _write(output_dir / "experiment_registry.jsonl", '{"experiment_id": "BT0001"}\n')
    after = source_code_state_hash([lib_dir], repo_root=tmp_path)
    assert before == after


def test_source_code_state_hash_returns_none_for_empty_source_set(tmp_path: Path) -> None:
    missing_dir = tmp_path / "does_not_exist"
    assert source_code_state_hash([missing_dir], repo_root=tmp_path) is None


def test_source_code_state_hash_can_include_a_single_script_file(tmp_path: Path) -> None:
    """呼び出し側の実行Script自身(単一ファイル)もSourceパスとして渡せる。"""
    script_path = tmp_path / "run.py"
    _write(script_path, "print('hello')\n")
    result = source_code_state_hash([script_path], repo_root=tmp_path)
    assert result is not None
