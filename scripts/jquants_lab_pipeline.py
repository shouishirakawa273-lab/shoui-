"""Japanese Equity Research Lab — Pipeline実行スクリプト(Phase3A: 実データ対応)。

Data -> Feature -> Signal -> Decision -> Execution -> Return -> Benchmark比較 ->
Experiment Registry を一本通しで実行し、Raw SnapshotとProvenanceを記録する。

--source jquants はローカル環境で(.envにJQUANTS_REFRESH_TOKENを設定した上で)実行すること
(クラウドのセッションからは外部APIへ接続できないことがある。README.md参照)。
--source local は、ネットワーク接続できる別環境で取得済みのJ-Quants生レスポンス
(JSON/CSV)をこの環境へ持ち込んで実行するためのモード
(lib/data_sources/local_snapshot.LocalSnapshotAdapter、ファイル命名規約はdocstring参照)。
--source fixture は合成データによるPipeline配線の検証用で、ネットワーク接続なしで
どこでも実行できる(Strategy Performance評価には使わない)。

使い方:
    python scripts/jquants_lab_pipeline.py --source fixture
    python scripts/jquants_lab_pipeline.py --source jquants --codes 7203 6758 8056 3626 \
        --benchmark-index-code 0000 --start 2024-01-04 --end 2026-07-24
    python scripts/jquants_lab_pipeline.py --source local --local-snapshot-dir /path/to/snapshots \
        --codes 7203 6758 8056 3626 --benchmark-index-code 0000 --start 2024-01-04 --end 2026-07-24
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
from lib.data_sources.base import DataSourceAdapter  # noqa: E402
from lib.data_sources.convert import (  # noqa: E402
    daily_quotes_payload_to_raw_bars,
    detect_split_hints_from_daily_quotes,
    index_prices_payload_to_raw_bars,
    listed_info_payload_to_listing_records,
    trading_calendar_payload_to_calendar,
)
from lib.data_sources.fixture import FixtureDataSourceAdapter  # noqa: E402
from lib.data_sources.jquants import JQuantsAdapter  # noqa: E402
from lib.data_sources.local_snapshot import LocalSnapshotAdapter  # noqa: E402
from lib.market_calendar import session_close_at  # noqa: E402
from lib.registry.experiment_registry import ExperimentRegistry  # noqa: E402
from lib.registry.provenance import ProvenanceLink, ProvenanceStore  # noqa: E402
from lib.reproducibility import current_code_commit, dataset_hash_from_snapshots, hash_json_safe, is_git_dirty  # noqa: E402
from lib.schemas.experiment import Experiment, ExperimentStatus, ReproducibilityFingerprint  # noqa: E402
from lib.schemas.hypothesis import Hypothesis  # noqa: E402
from lib.schemas.price_data import apply_split_adjustments  # noqa: E402
from lib.snapshot import RawSnapshotStore  # noqa: E402
from lib.strategies.fixed_pipeline_validation import (  # noqa: E402
    DEFAULT_CONFIG,
    STRATEGY_ID,
    STRATEGY_VERSION,
    as_buy_signal_fn,
)
from lib.universe import ListingBasedUniverseProvider  # noqa: E402


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
    benchmark_index_code: str,
    start: date,
    end: date,
    fixture_path: Path,
    local_snapshot_dir: Path | None,
    commission_bps: float,
    slippage_bps: float,
) -> None:
    is_real_source = source in ("jquants", "local")
    if is_real_source:
        print(
            "!!! BLOCKING TODO(実日本株Backtestでは未解決) !!!\n"
            "Corporate Actions(株式分割・併合等)のannounced_at付きデータSourceが未実装のため、\n"
            "対象期間・対象銘柄に分割等があった場合、価格系列が不連続になり\n"
            "Backtest結果が誤ります。実際の投資判断にこの結果を使用しないでください。\n"
            "(DECISIONS.md D0014/D0025、RESEARCH_RULES.md参照)\n"
        )

    load_dotenv()
    adapter = _build_adapter(source, fixture_path, local_snapshot_dir)
    snapshot_store = RawSnapshotStore(_LAB_DIR / "01_data" / "raw")
    run_id = f"RUN_{datetime.now(UTC):%Y%m%dT%H%M%S%f}"
    manifests_used = []

    quotes_result = adapter.fetch_daily_quotes(codes=codes, start_date=start, end_date=end)
    calendar_result = adapter.fetch_trading_calendar(start_date=start, end_date=end)
    quotes_manifest = snapshot_store.save(quotes_result, snapshot_id=f"SNAP_{run_id}_daily_quotes")
    calendar_manifest = snapshot_store.save(calendar_result, snapshot_id=f"SNAP_{run_id}_trading_calendar")
    manifests_used += [quotes_manifest, calendar_manifest]

    raw_bars = daily_quotes_payload_to_raw_bars(quotes_result.payload, source=source)
    raw_by_code: dict[str, list] = {}
    for bar in raw_bars:
        raw_by_code.setdefault(bar.code, []).append(bar)

    # BLOCKING TODO(Phase3B以降): Corporate Actionsのannounced_at付きSourceが未実装のため、
    # 現時点ではsplit調整なし(actions=[])でRaw->Adjustedへ明示的に変換している
    # (RawとAdjustedを混同しない、という設計自体は満たすが、分割があった銘柄では
    # 価格が不連続になりうる)。AdjustmentFactorからの検出候補は情報提供のみ行う。
    price_history = {code: apply_split_adjustments(bars, []) for code, bars in raw_by_code.items()}
    corporate_action_hints = detect_split_hints_from_daily_quotes(quotes_result.payload)

    # Benchmark: fixtureモードは従来通りdaily_quotesベースの擬似コード(後方互換)、
    # jquants/localモードは実Indexデータ(/indices)を使う。
    if source == "fixture":
        benchmark_result = adapter.fetch_daily_quotes(codes=[benchmark_code], start_date=start, end_date=end)
        benchmark_manifest = snapshot_store.save(benchmark_result, snapshot_id=f"SNAP_{run_id}_benchmark")
        benchmark_raw_bars = daily_quotes_payload_to_raw_bars(benchmark_result.payload, source=source)
        benchmark_label = benchmark_code
    else:
        benchmark_result = adapter.fetch_index_prices(index_code=benchmark_index_code, start_date=start, end_date=end)
        benchmark_manifest = snapshot_store.save(benchmark_result, snapshot_id=f"SNAP_{run_id}_benchmark_index")
        benchmark_raw_bars = index_prices_payload_to_raw_bars(benchmark_result.payload, code=benchmark_index_code, source=source)
        benchmark_label = benchmark_index_code
    manifests_used.append(benchmark_manifest)
    benchmark_bars = apply_split_adjustments(benchmark_raw_bars, [])

    trading_calendar = trading_calendar_payload_to_calendar(calendar_result.payload, range_start=start, range_end=end)

    # Universe: 実データSourceのみ接続する(fixtureモードでは省略、DATA_UNAVAILABLE扱い)。
    universe_snapshot = None
    if is_real_source:
        listed_info_result = adapter.fetch_listed_info()
        listed_info_manifest = snapshot_store.save(listed_info_result, snapshot_id=f"SNAP_{run_id}_listed_info")
        manifests_used.append(listed_info_manifest)
        listing_records = listed_info_payload_to_listing_records(listed_info_result.payload)
        universe_provider = ListingBasedUniverseProvider(listing_records)
        universe_snapshot = universe_provider.as_of(session_close_at(end))

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
    )
    if git_dirty:
        print(
            "警告: working treeに未コミットの変更があります。"
            "code_commitが指すコミット内容と実行時のコードが一致しないため、"
            "完全な再現性は保証されません。"
        )

    experiment = Experiment(
        experiment_id=f"BT_{run_id}",
        hypothesis_id=hypothesis.hypothesis_id,
        strategy_id=STRATEGY_ID,
        status=ExperimentStatus.TESTED,
        metrics=metrics,
        reproducibility=fingerprint,
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
    print(
        f"corporate action hints(情報提供のみ、Backtestには未適用): {len(corporate_action_hints)}件 "
        f"({[h.code for h in corporate_action_hints]})"
    )
    if universe_snapshot is not None:
        print(
            f"universe: resolution={universe_snapshot.resolution.value} "
            f"codes={len(universe_snapshot.codes)}件 "
            f"survivorship_bias_unresolved={universe_snapshot.survivorship_bias_unresolved} "
            f"note={universe_snapshot.note!r}"
        )
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
    parser.add_argument(
        "--benchmark-index-code",
        default="0000",
        help="--source jquants/local 用のTOPIX等インデックスコード(未検証、要ローカル確認)",
    )
    parser.add_argument("--start", type=date.fromisoformat, default=date(2026, 1, 5))
    parser.add_argument("--end", type=date.fromisoformat, default=date(2026, 6, 30))
    parser.add_argument(
        "--fixture-path",
        type=Path,
        default=_LAB_DIR / "13_tests" / "fixtures" / "synthetic_jquants_daily_quotes.json",
    )
    parser.add_argument(
        "--local-snapshot-dir",
        type=Path,
        default=None,
        help="--source local 用。ローカル環境で取得したJ-Quants生レスポンスを置いたディレクトリ",
    )
    parser.add_argument("--commission-bps", type=float, default=5.0)
    parser.add_argument("--slippage-bps", type=float, default=5.0)
    args = parser.parse_args()

    run_pipeline(
        source=args.source,
        codes=args.codes,
        benchmark_code=args.benchmark_code,
        benchmark_index_code=args.benchmark_index_code,
        start=args.start,
        end=args.end,
        fixture_path=args.fixture_path,
        local_snapshot_dir=args.local_snapshot_dir,
        commission_bps=args.commission_bps,
        slippage_bps=args.slippage_bps,
    )


if __name__ == "__main__":
    main()
