"""Japanese Equity Research Lab — Pipeline実行スクリプト(J-Quants API V2対応)。

Data -> Feature -> Signal -> Decision -> Execution -> Return -> Benchmark比較 ->
Experiment Registry を一本通しで実行し、Raw SnapshotとProvenanceを記録する。

--source jquants はローカル環境で(.envにJQUANTS_API_KEYを設定した上で)実行すること
(クラウドのセッションからは外部API・公式ドキュメントへ接続できないことがある。
README.md参照)。
--source local は、ネットワーク接続できる別環境で取得済みのJ-Quants V2生レスポンス
(JSON/CSV)をこの環境へ持ち込んで実行するためのモード
(lib/data_sources/local_snapshot.LocalSnapshotAdapter、ファイル命名規約はdocstring参照。
LOCAL_DATA_FETCH_GUIDE.mdも参照)。
--source fixture は合成データによるPipeline配線の検証用で、ネットワーク接続なしで
どこでも実行できる(Strategy Performance評価には使わない)。

--price-adjustment pit(既定、実データBacktestで推奨)は、decision_atごとにPIT-safeな
As-of Adjustment(`AsOfAdjustedPriceHistory`、D0034/D0035)を使う。
--price-adjustment none は無調整のまま(Phase3A.1以前と同じ、`StaticPriceHistory`)。
いずれもCorporate Action Announcementを取引Signalとして使う機能(Case A)ではない
(Price Series連続化専用、Case B)。Case Aはannounced_at付きデータSourceが無いため
引き続き未実装。

使い方:
    python scripts/jquants_lab_pipeline.py --source fixture
    python scripts/jquants_lab_pipeline.py --source jquants --codes 7203 6758 8056 3626 \
        --start 2024-01-04 --end 2026-07-24
    python scripts/jquants_lab_pipeline.py --source local --local-snapshot-dir /path/to/snapshots \
        --codes 7203 6758 8056 3626 --start 2024-01-04 --end 2026-07-24 --price-adjustment none
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_LAB_DIR = _REPO_ROOT / "Japanese_Equity_Lab"
sys.path.insert(0, str(_LAB_DIR))

from dotenv import load_dotenv  # noqa: E402
from lib.backtest.engine import BacktestEngine, BacktestRunConfig, TransactionCostConfig  # noqa: E402
from lib.backtest.price_history import AsOfAdjustedPriceHistory, PriceHistorySource, StaticPriceHistory  # noqa: E402
from lib.data_sources.base import DataSourceAdapter  # noqa: E402
from lib.data_sources.convert import (  # noqa: E402
    detect_corporate_action_events_from_equity_bars,
    equities_master_payload_to_listing_records,
    equity_bars_payload_to_raw_bars,
    topix_bars_payload_to_raw_bars,
    trading_calendar_payload_to_calendar,
)
from lib.data_sources.fixture import FixtureDataSourceAdapter  # noqa: E402
from lib.data_sources.jquants import JQuantsAdapter  # noqa: E402
from lib.data_sources.local_snapshot import LocalSnapshotAdapter  # noqa: E402
from lib.market_calendar import session_close_at  # noqa: E402
from lib.registry.experiment_registry import ExperimentRegistry  # noqa: E402
from lib.registry.provenance import ProvenanceLink, ProvenanceStore  # noqa: E402
from lib.reproducibility import (  # noqa: E402
    current_code_commit,
    dataset_hash_from_snapshots,
    hash_json_safe,
    is_git_dirty,
    source_code_state_hash,
)
from lib.schemas.experiment import (  # noqa: E402
    Experiment,
    ExperimentStatus,
    PriceAdjustmentProvenance,
    ReproducibilityFingerprint,
)
from lib.schemas.hypothesis import Hypothesis  # noqa: E402
from lib.schemas.price_data import apply_split_adjustments  # noqa: E402
from lib.snapshot import RawSnapshotStore  # noqa: E402
from lib.strategies.fixed_pipeline_validation import (  # noqa: E402
    DEFAULT_CONFIG,
    STRATEGY_ID,
    STRATEGY_VERSION,
    as_buy_signal_fn,
)
from lib.universe import ListingBasedUniverseProvider, check_company_name_consistency  # noqa: E402


def _build_adapter(source: str, fixture_path: Path, local_snapshot_dir: Path | None) -> DataSourceAdapter:
    if source == "fixture":
        return FixtureDataSourceAdapter(fixture_path)
    if source == "local":
        if local_snapshot_dir is None:
            raise SystemExit("--source local には --local-snapshot-dir の指定が必須です。")
        return LocalSnapshotAdapter(local_snapshot_dir)
    return JQuantsAdapter()


def run_pipeline(
    *,
    source: str,
    codes: list[str],
    benchmark_code: str,
    start: date,
    end: date,
    fixture_path: Path,
    local_snapshot_dir: Path | None,
    commission_bps: float,
    slippage_bps: float,
    price_adjustment: str = "pit",
    expected_company_names: dict[str, str] | None = None,
) -> None:
    is_real_source = source in ("jquants", "local")
    print(
        "!!! 未実装(Case A) !!!\n"
        "Corporate Action Announcement(公表)をSignalとして使う用途(Case A)の\n"
        "データSourceは未実装のため、この用途には使用できません(announced_atが必要)。\n"
        "一方、Price Series連続化(Case B)はPIT-safeに実装済みで、--price-adjustment pit\n"
        "(既定)により decision_atごとに正しく適用されます(DECISIONS.md D0034/D0035)。\n"
    )
    if is_real_source and source == "jquants":
        print(
            "現在の契約プランはLightと申告されています。daily_prices/trading_calendar/"
            "topix/listed_masterはLightプランでも利用可能と想定していますが未検証です"
            "(DataSourceCapabilities、DECISIONS.md D0033参照)。\n"
        )

    load_dotenv()
    adapter = _build_adapter(source, fixture_path, local_snapshot_dir)
    snapshot_store = RawSnapshotStore(_LAB_DIR / "01_data" / "raw")
    run_id = f"RUN_{datetime.now(UTC):%Y%m%dT%H%M%S%f}"
    manifests_used = []

    quotes_result = adapter.fetch_equity_bars(codes=codes, start_date=start, end_date=end)
    calendar_result = adapter.fetch_trading_calendar(start_date=start, end_date=end)
    quotes_manifest = snapshot_store.save(quotes_result, snapshot_id=f"SNAP_{run_id}_equity_bars")
    calendar_manifest = snapshot_store.save(calendar_result, snapshot_id=f"SNAP_{run_id}_trading_calendar")
    manifests_used += [quotes_manifest, calendar_manifest]

    raw_bars = equity_bars_payload_to_raw_bars(quotes_result.payload, source=source)
    raw_by_code: dict[str, list] = {}
    for bar in raw_bars:
        raw_by_code.setdefault(bar.code, []).append(bar)

    # Corporate Action Event(V2 AdjFactor/ExRT由来)を銘柄ごとにグルーピングする。
    # Case A(Announcementを使う用途)のデータSourceは未実装のまま(announced_atが必要)。
    corporate_action_events = detect_corporate_action_events_from_equity_bars(quotes_result.payload)
    events_by_code: dict[str, list] = {code: [] for code in codes}
    for event in corporate_action_events:
        events_by_code.setdefault(event.code, []).append(event)

    price_history: PriceHistorySource
    if price_adjustment == "pit":
        # decision_atごとにPIT-safeなAs-of Adjustmentを適用する(D0034/D0035)。
        # 全期間共通の事前計算済みAdjusted Seriesを保持・使い回すことはしない。
        price_history = AsOfAdjustedPriceHistory(raw_by_code, events_by_code)
    else:
        price_history = StaticPriceHistory({code: apply_split_adjustments(bars, []) for code, bars in raw_by_code.items()})

    # Benchmark: fixtureモードは従来通りequity_barsベースの擬似コード(後方互換)、
    # jquants/localモードはTOPIX専用Endpoint(/v2/indices/bars/daily/topix)を使う。
    if source == "fixture":
        benchmark_result = adapter.fetch_equity_bars(codes=[benchmark_code], start_date=start, end_date=end)
        benchmark_manifest = snapshot_store.save(benchmark_result, snapshot_id=f"SNAP_{run_id}_benchmark")
        benchmark_raw_bars = equity_bars_payload_to_raw_bars(benchmark_result.payload, source=source)
        benchmark_label = benchmark_code
    else:
        benchmark_result = adapter.fetch_topix_bars(start_date=start, end_date=end)
        benchmark_manifest = snapshot_store.save(benchmark_result, snapshot_id=f"SNAP_{run_id}_topix")
        benchmark_raw_bars = topix_bars_payload_to_raw_bars(benchmark_result.payload, source=source)
        benchmark_label = "TOPIX"
    manifests_used.append(benchmark_manifest)
    benchmark_bars = apply_split_adjustments(benchmark_raw_bars, [])

    trading_calendar = trading_calendar_payload_to_calendar(calendar_result.payload, range_start=start, range_end=end)

    # Universe: 実データSourceのみ接続する(fixtureモードでは省略、DATA_UNAVAILABLE扱い)。
    # decision_atごとにuniverse_provider.as_of()を再解決させ(単一の事前計算Snapshotを
    # 使い回さない、D0038)、上場廃止後の銘柄はSignal自体の対象から外す
    # (Japanese_Equity_Lab/lib/backtest/engine.pyのuniverse_provider配線を参照)。
    universe_snapshot = None
    universe_provider: ListingBasedUniverseProvider | None = None
    name_warnings: list[str] = []
    if is_real_source:
        master_result = adapter.fetch_equities_master()
        master_manifest = snapshot_store.save(master_result, snapshot_id=f"SNAP_{run_id}_equities_master")
        manifests_used.append(master_manifest)
        listing_records = equities_master_payload_to_listing_records(master_result.payload)
        universe_provider = ListingBasedUniverseProvider(listing_records)
        universe_snapshot = universe_provider.as_of(session_close_at(end))
        if expected_company_names:
            name_warnings = check_company_name_consistency(expected_company_names, listing_records)

    run_config = BacktestRunConfig(
        universe_codes=tuple(codes),
        start_session=start,
        end_session=end,
        holding_period_days=DEFAULT_CONFIG.holding_period_days,
        transaction_cost=TransactionCostConfig(commission_bps=commission_bps, slippage_bps=slippage_bps),
    )

    engine = BacktestEngine()
    metrics = engine.run(
        config=run_config,
        price_history=price_history,
        benchmark_bars=benchmark_bars,
        trading_calendar=trading_calendar,
        signal_fn=as_buy_signal_fn(),
        universe_provider=universe_provider,
    )

    hypothesis = Hypothesis(
        hypothesis_id=f"H_{STRATEGY_ID}",
        source_idea_id=None,
        claim="20営業日Price Returnが正の銘柄は、その後もモメンタムが続く",
        mechanism="Pipeline検証専用の固定仮説(経済的メカニズムの主張はしない、パラメータ探索もしない)",
        universe=",".join(codes),
        signal_definition="20営業日Price Return > 0",
        entry_rule="次営業日Openで買い",
        exit_rule=f"{DEFAULT_CONFIG.holding_period_days}営業日後Openで手仕舞い",
        holding_period=f"{DEFAULT_CONFIG.holding_period_days}営業日",
        success_metric="Pipelineが最後まで正常に動くこと(儲かることは評価対象ではない)",
        failure_metric="Pipelineのどこかでエラーになること",
    ).lock()

    dataset_hash = dataset_hash_from_snapshots([m.content_hash for m in manifests_used])
    strategy_hash = hash_json_safe({"strategy_id": STRATEGY_ID, "version": STRATEGY_VERSION, "config": asdict(DEFAULT_CONFIG)})
    config_hash = hash_json_safe(
        {
            "universe_codes": run_config.universe_codes,
            "start_session": run_config.start_session.isoformat(),
            "end_session": run_config.end_session.isoformat(),
            "holding_period_days": run_config.holding_period_days,
            "transaction_cost": asdict(run_config.transaction_cost),
        }
    )
    git_dirty = is_git_dirty(cwd=str(_REPO_ROOT))
    fingerprint = ReproducibilityFingerprint(
        run_id=run_id,
        dataset_hash=dataset_hash,
        strategy_hash=strategy_hash,
        config_hash=config_hash,
        code_commit=current_code_commit(cwd=str(_REPO_ROOT)),
        git_dirty=git_dirty,
        source_code_state_hash=source_code_state_hash([_LAB_DIR / "lib", Path(__file__)], repo_root=_REPO_ROOT),
    )
    if git_dirty:
        print(
            "警告: working treeに未コミットの変更があります。"
            "code_commitが指すコミット内容と実行時のコードが一致しないため、"
            "完全な再現性は保証されません。"
        )

    price_adjustment_provenance = PriceAdjustmentProvenance(
        adjustment_method=("PIT_AS_OF_ADJFACTOR_V1" if price_adjustment == "pit" else "NONE"),
        as_of_policy=("decision_at" if price_adjustment == "pit" else "static"),
        corporate_action_source=("jquants_v2_adjfactor" if is_real_source else "none"),
        raw_snapshot_ids=(quotes_manifest.snapshot_id,),
    )
    experiment = Experiment(
        experiment_id=f"BT_{run_id}",
        hypothesis_id=hypothesis.hypothesis_id,
        strategy_id=STRATEGY_ID,
        status=ExperimentStatus.TESTED,
        metrics=metrics,
        reproducibility=fingerprint,
        price_adjustment=price_adjustment_provenance,
        notes=f"source={source}",
    )
    ExperimentRegistry(_LAB_DIR / "06_backtests" / "experiment_registry.jsonl").record(experiment)

    provenance = ProvenanceStore(_LAB_DIR / "06_backtests" / "provenance.jsonl")
    processed_dataset_id = f"PD_{dataset_hash[:16]}"
    provenance.add_link(
        ProvenanceLink(
            link_id=f"L_{run_id}_1",
            from_type="source_request",
            from_id=f"REQ_{quotes_manifest.snapshot_id}",
            to_type="raw_snapshot",
            to_id=quotes_manifest.snapshot_id,
        )
    )
    provenance.add_link(
        ProvenanceLink(
            link_id=f"L_{run_id}_2",
            from_type="raw_snapshot",
            from_id=quotes_manifest.snapshot_id,
            to_type="processed_dataset",
            to_id=processed_dataset_id,
        )
    )
    provenance.add_link(
        ProvenanceLink(
            link_id=f"L_{run_id}_3",
            from_type="processed_dataset",
            from_id=processed_dataset_id,
            to_type="strategy",
            to_id=STRATEGY_ID,
        )
    )
    provenance.add_link(
        ProvenanceLink(
            link_id=f"L_{run_id}_4",
            from_type="strategy",
            from_id=STRATEGY_ID,
            to_type="hypothesis",
            to_id=hypothesis.hypothesis_id,
        )
    )
    provenance.add_link(
        ProvenanceLink(
            link_id=f"L_{run_id}_5",
            from_type="hypothesis",
            from_id=hypothesis.hypothesis_id,
            to_type="experiment",
            to_id=experiment.experiment_id,
        )
    )

    print(f"=== run_id={run_id} (source={source}) ===")
    print(f"universe_codes={run_config.universe_codes} benchmark={benchmark_label}")
    print(f"period={start}〜{end}")
    print(f"quotes snapshot: {quotes_manifest.snapshot_id} (record_count={quotes_manifest.record_count})")
    print(f"calendar snapshot: {calendar_manifest.snapshot_id} (record_count={calendar_manifest.record_count})")
    print(f"benchmark snapshot: {benchmark_manifest.snapshot_id} (record_count={benchmark_manifest.record_count})")
    if price_adjustment == "pit":
        applied_note = "PIT-safeにBacktestへ適用済み(decision_atごとのAs-of Adjustment)"
    else:
        applied_note = "情報提供のみ、Backtestには未適用"
    event_codes = [e.code for e in corporate_action_events]
    print(f"corporate action events({applied_note}): {len(corporate_action_events)}件 ({event_codes})")
    print(f"price_adjustment={price_adjustment} adjustment_method={price_adjustment_provenance.adjustment_method}")
    if universe_snapshot is not None:
        print(
            f"universe(end={end}時点の参考Snapshot): resolution={universe_snapshot.resolution.value} "
            f"codes={len(universe_snapshot.codes)}件 "
            f"survivorship_bias_unresolved={universe_snapshot.survivorship_bias_unresolved} "
            f"note={universe_snapshot.note!r}"
        )
        print(
            "universe: decision_atごとの適格性判定はBacktestへ適用済み"
            "(universe_provider.as_of(decision_at)、上場廃止日以降はSignal自体を評価しない。"
            "上記のSnapshotは末尾日end時点の参考表示に過ぎず、実際に各decision_atで使われた"
            "判定そのものではない)"
        )
    if name_warnings:
        print(f"company name consistency warnings: {name_warnings}")
    print(f"experiment_id={experiment.experiment_id} status={experiment.status.value}")
    print(f"metrics={metrics}")
    print(f"reproducibility={fingerprint}")

    chain = provenance.trace_to_origin("experiment", experiment.experiment_id)
    print("provenance chain (source_request -> ... -> experiment):")
    for link in chain:
        print(f"  {link.from_type}:{link.from_id} -> {link.to_type}:{link.to_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", choices=["jquants", "fixture", "local"], default="fixture")
    parser.add_argument("--codes", nargs="+", default=["7203", "6758", "9984"])
    parser.add_argument("--benchmark-code", default="TOPIX_SYNTH", help="--source fixture 専用の擬似Benchmarkコード")
    parser.add_argument("--start", type=date.fromisoformat, default=date(2026, 1, 5))
    parser.add_argument("--end", type=date.fromisoformat, default=date(2026, 6, 30))
    parser.add_argument(
        "--fixture-path",
        type=Path,
        default=_LAB_DIR / "13_tests" / "fixtures" / "synthetic_jquants_v2_bars.json",
    )
    parser.add_argument(
        "--local-snapshot-dir",
        type=Path,
        default=None,
        help="--source local 用。ローカル環境で取得したJ-Quants V2生レスポンスを置いたディレクトリ",
    )
    parser.add_argument("--commission-bps", type=float, default=5.0)
    parser.add_argument("--slippage-bps", type=float, default=5.0)
    parser.add_argument(
        "--price-adjustment",
        choices=["none", "pit"],
        default="pit",
        help="pit(既定): decision_atごとのPIT-safe As-of Adjustmentを適用(D0034/D0035)。"
        "none: 無調整のまま(Phase3A.1以前と同じ)。",
    )
    args = parser.parse_args()

    run_pipeline(
        source=args.source,
        codes=args.codes,
        benchmark_code=args.benchmark_code,
        start=args.start,
        end=args.end,
        fixture_path=args.fixture_path,
        local_snapshot_dir=args.local_snapshot_dir,
        commission_bps=args.commission_bps,
        slippage_bps=args.slippage_bps,
        price_adjustment=args.price_adjustment,
    )


if __name__ == "__main__":
    main()
