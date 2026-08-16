"""Reproducibility: 同じRaw Snapshot・同じStrategy version・同じConfig・同じCode version
であれば同じBacktest結果になることを検証するためのhash計算ユーティリティ。

数値を推測で埋めない方針に合わせ、`code_commit`が取得できない場合は`None`のままにし、
架空のコミットIDを生成しない。
"""

from __future__ import annotations

import hashlib
import json
import subprocess
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
