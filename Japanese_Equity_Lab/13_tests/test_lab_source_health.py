"""Lightweight System Health診断Script(4A.5.1-9、`scripts/lab_source_health.py`)の
回帰Test。Scriptは読み取り専用でExit Code/Output文字列を確認するのみ
(新規DB/Daemon/Serverを導入しないという設計の直接確認も兼ねる)。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "lab_source_health.py"


def _run_script() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(_SCRIPT)],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
        timeout=30,
        check=False,
    )


def test_script_exits_zero_and_makes_no_network_call() -> None:
    """外部APIへ一切接続しない(既存Fixture Snapshotのみを読む)ため、この
    Sessionのネットワーク制約下でも常に成功すること。"""
    result = _run_script()
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_script_reports_dataset_catalog_status() -> None:
    result = _run_script()
    assert "Dataset Implementation Status" in result.stdout
    for dataset_id in ("jquants_fins_summary", "disclosure_common_core", "edinet_disclosures", "tdnet_disclosures"):
        assert dataset_id in result.stdout, f"{dataset_id} がOutputに含まれていません"


def test_script_reports_raw_snapshot_freshness_including_fixture() -> None:
    """`01_data/raw/fixture/`はGit追跡対象(実Providerのraw dataとは異なり
    `.gitignore`対象ではない)であり、常に存在する。この既存Fixtureに対して
    実際にManifestを読み取れることを確認する(Vacuousでない、実File経由の
    確認)。"""
    result = _run_script()
    assert "Raw Snapshot Freshness" in result.stdout
    assert "fixture: snapshot件数=" in result.stdout
    assert "最新のretrieved_at:" in result.stdout


def test_script_never_asserts_automatic_anomaly_judgment() -> None:
    """このScriptは異常の自動判定・Alert発報を行わない設計(Output自体に
    その旨を明記する)ことを確認する(設計原則のRegression化)。"""
    result = _run_script()
    assert "異常の自動判定" in result.stdout
