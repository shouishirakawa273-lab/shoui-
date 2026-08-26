"""Reproducibility: 同じRaw Snapshot・同じStrategy version・同じConfig・同じCode version
であれば同じBacktest結果になることを検証するためのhash計算ユーティリティ。

数値を推測で埋めない方針に合わせ、`code_commit`が取得できない場合は`None`のままにし、
架空のコミットIDを生成しない。
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Iterable
from pathlib import Path
from typing import Any


def hash_json_safe(value: Any) -> str:
    """JSON化可能な値からcanonicalなSHA-256 hashを計算する(キー順序を固定する)。"""
    canonical = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def dataset_hash_from_snapshots(content_hashes: list[str]) -> str:
    """使用した全Raw Snapshotのcontent_hashから、データセット全体のhashを導出する。"""
    return hash_json_safe(sorted(content_hashes))


def current_code_commit(*, cwd: str | None = None) -> str | None:
    """現在のgit commit hashを取得する。取得できない場合はNoneを返す(推測で埋めない)。"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
            cwd=cwd,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    commit = result.stdout.strip()
    return commit or None


def source_code_state_hash(paths: Iterable[Path], *, repo_root: Path) -> str | None:
    """指定したファイル/ディレクトリ配下の`*.py`の内容から、実行時点の研究コードの
    状態を表すhashを計算する(Post-Phase5 Hardening A、D0069)。

    `code_commit`+`git_dirty`だけでは、dirty=Trueの場合に実際どこがcommitと
    異なるのかが分からない。かといって「dirtyなら実行禁止」にはしない
    (Experiment RegistryやReportの生成自体がこのRunのworking treeを変化させる
    ため、Run開始前にcleanでもRun自体が終わる頃にはdirtyになりうる。生成物を
    追跡しないための機械的な回避として「commit前にhashを取る」ではなく、そもそも
    「対象パスに生成物を含めない」設計にする)。

    このため、gitのcommit状態やdiffではなく、呼び出し側が明示的に指定した
    Sourceパス(通常はlib/ディレクトリと実行中のScript自身)配下の`*.py`
    ファイル内容だけを対象にする。生成物ディレクトリ(06_backtests/・12_reports/等)
    や`.env`・raw dataは対象パスに含めない限りhash入力に混入しない
    (呼び出し側がlib/scriptsのみを渡す限り、これらは構造的に除外される)。
    gitが無い環境でも動作する(subprocess呼び出しを行わない)。
    """
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(path.rglob("*.py"))
        elif path.is_file():
            files.append(path)
    if not files:
        return None
    repo_root_resolved = repo_root.resolve()
    entries: list[list[str]] = []
    for file_path in sorted(set(files)):
        resolved = file_path.resolve()
        try:
            relative = resolved.relative_to(repo_root_resolved).as_posix()
        except ValueError:
            relative = resolved.as_posix()
        content_hash = hashlib.sha256(resolved.read_bytes()).hexdigest()
        entries.append([relative, content_hash])
    return hash_json_safe(sorted(entries))


def is_git_dirty(*, cwd: str | None = None) -> bool | None:
    """working treeに未コミットの変更(untracked含む)があるかを返す。

    Trueの場合、`code_commit`が指すコミットの内容とその実行時のコード内容が完全には
    一致していない可能性があり、完全な再現性は保証されない(呼び出し側はこのフラグを
    ユーザーに明示すること)。gitが使えない等で判定できない場合はNoneを返す
    (推測で埋めない)。
    """
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
            cwd=cwd,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return bool(result.stdout.strip())
