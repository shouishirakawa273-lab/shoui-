"""Japanese Equity Lab向けのLightweight System Health診断Script(4A.5.1-9)。

既存の`SourceCatalog`(Dataset実装状況)と`RawSnapshotStore`が書き出す
Manifest File(`01_data/raw/*/*.manifest.json`)を読むだけの、完全に
読み取り専用のScriptである。新規DB・新規Daemon・新規Serverは一切
導入しない(Grafana/Prometheus等の大規模Observability Infrastructureは
このLabの規模には過剰、`PHASE4A5_1_PLAN.md` §L参照)。

外部APIへは一切接続しない(ローカルFileを読むのみ)。数値の異常検知・
自動判定Logicは持たない(人間が目視で状況を把握するための表示のみ)。

使い方:
    python scripts/lab_source_health.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_LAB_DIR = _REPO_ROOT / "Japanese_Equity_Lab"
sys.path.insert(0, str(_LAB_DIR))

from lib.disclosures.catalog import (  # noqa: E402
    build_disclosure_common_core_dataset_descriptor,
    build_edinet_dataset_descriptor,
    build_tdnet_dataset_descriptor,
)
from lib.fundamentals.catalog import build_financial_summary_dataset_descriptor  # noqa: E402
from lib.sources.catalog import SourceCatalog  # noqa: E402


def _build_catalog() -> SourceCatalog:
    return SourceCatalog(
        (
            build_financial_summary_dataset_descriptor(),
            build_disclosure_common_core_dataset_descriptor(),
            build_edinet_dataset_descriptor(),
            build_tdnet_dataset_descriptor(),
        )
    )


def _print_catalog_status(catalog: SourceCatalog) -> None:
    print("=== Dataset Implementation Status(SourceCatalog) ===")
    for dataset in catalog.all():
        print(f"- {dataset.dataset_id}")
        print(f"    capability={dataset.capability.value} status={dataset.implementation_status.value}")
        if dataset.known_limitations:
            limitations = dataset.known_limitations.replace("\n", " ")
            preview = limitations[:120] + ("..." if len(limitations) > 120 else "")
            print(f"    known_limitations: {preview}")
    print()


def _scan_raw_snapshots(raw_dir: Path) -> None:
    print("=== Raw Snapshot Freshness(RawSnapshotStore Manifest) ===")
    if not raw_dir.exists():
        print(f"(未確認: {raw_dir} が存在しません)")
        print()
        return

    source_dirs = sorted(p for p in raw_dir.iterdir() if p.is_dir())
    if not source_dirs:
        print("(Snapshot Sourceディレクトリが1件もありません)")
        print()
        return

    for source_dir in source_dirs:
        manifests = sorted(source_dir.glob("*.manifest.json"))
        if not manifests:
            print(f"- {source_dir.name}: Manifestなし")
            continue

        retrieved_ats: list[datetime] = []
        for manifest_path in manifests:
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                retrieved_at_raw = data.get("retrieved_at")
                if retrieved_at_raw:
                    retrieved_ats.append(datetime.fromisoformat(retrieved_at_raw))
            except (json.JSONDecodeError, ValueError, OSError):
                # 診断専用Scriptであり、壊れたManifestで全体を止めない
                # (Fail Closedにしない、目視確認の補助にすぎないため)。
                continue

        print(f"- {source_dir.name}: snapshot件数={len(manifests)}")
        if retrieved_ats:
            print(f"    最古のretrieved_at: {min(retrieved_ats).isoformat()}")
            print(f"    最新のretrieved_at: {max(retrieved_ats).isoformat()}")
        else:
            print("    (retrieved_atを読み取れたManifestがありません)")
    print()


def main() -> None:
    catalog = _build_catalog()
    _print_catalog_status(catalog)
    _scan_raw_snapshots(_LAB_DIR / "01_data" / "raw")
    print("(このScriptは読み取り専用の目視確認補助であり、異常の自動判定・")
    print(" Alert発報・数値の妥当性評価は一切行わない)")


if __name__ == "__main__":
    main()
