"""JQS-STD-02: 7203 Historical Valuation Contextを、Standard-era(JQS-STD-01で
確認した拡張履歴)のRaw Dataで再測定する(Read/Write Measurement Script)。

**目的**: 現在のJ-Quants契約で取得可能なより長い履歴(価格/指数: 2016-09-08〜、
Financial Summary: 2016-11-08〜)を使った場合、`lib.valuation.
historical_context_builder.build_latest_reported_fy_per_historical_context()`
(Stage 3.15、D0089/D0090、既存Production Logic、無変更)が返すHistorical
Sample数・分布が、Frozen Stage 3.15 Artifact(n=30、2022-05-31〜2024-10-31、
`scripts/verify_stage3_15_7203_closure.py`)と比べてどう変わるかを測定する。

**Scratchからのlogic Copy-Pasteは行わない**: `verify_stage3_15_7203_closure.py`
と同じOrchestration Pattern(既存Production API呼び出しのみ)を踏襲するが、
Evidence/Provenance/Registry/ResearchArtifact層は本Roundの目的(測定のみ)には
不要なため構築しない(`lib.valuation.*`のCore計算Functionのみ再利用する)。

**制約**:
- Frozen Stage 3.15 Artifact・その受入Harness(`scripts/verify_stage3_15_7203_
  closure.py`)・`01_data/raw/local_snapshot_input/`は一切変更・再実行しない
  (別Snapshot・別Snapshot IDを使う)。
- `02_company_research/`への書き込みは行わない(Out of Scope)。
- Positioning(Margin/Short/Investor Type等)は一切扱わない。
- Production Valuation Logic(`lib/valuation/*`)は無変更(呼ぶだけ)。
- H0001 Locked Testには一切触れない。

使い方:
    python scripts/jqs_std02_7203_historical_valuation_remeasurement.py
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parent.parent
LAB_ROOT = REPO_ROOT / "Japanese_Equity_Lab"
sys.path.insert(0, str(LAB_ROOT))

from dotenv import load_dotenv  # noqa: E402
from lib.data_sources.convert import (  # noqa: E402
    detect_corporate_action_events_from_equity_bars,
    equity_bars_payload_to_raw_bars,
    trading_calendar_payload_to_calendar,
)
from lib.data_sources.jquants import JQuantsAdapter  # noqa: E402
from lib.evidence.model import AvailabilitySemantics  # noqa: E402
from lib.fundamentals.model import ActualOrForecast, PeriodType  # noqa: E402
from lib.fundamentals.normalize import build_revision_histories, parse_financial_summary_payload  # noqa: E402
from lib.fundamentals.view import fundamentals_as_of  # noqa: E402
from lib.market_calendar import session_close_at  # noqa: E402
from lib.snapshot import RawSnapshotStore  # noqa: E402
from lib.valuation.builder import (  # noqa: E402
    build_latest_reported_fy_per,
    has_share_basis_action_in_window,
    select_latest_close_bar,
)
from lib.valuation.historical_context_builder import build_latest_reported_fy_per_historical_context  # noqa: E402

_JST = ZoneInfo("Asia/Tokyo")
_ENTITY = "7203"
_AS_OF = datetime(2024, 11, 15, 15, 0, tzinfo=_JST)  # Stage 3.15と同一As-Of Target(§7)
_PRICE_START = date(2016, 9, 8)  # JQS-STD-01 confirmed boundary
_PRICE_END = date(2025, 1, 31)  # As-Ofより十分後(バッファ)
_FINS_START = date(2016, 1, 1)  # Financial Summaryはfrom/toで絞り込まれない(D0043/JQS-STD-01確認済み)
_FINS_END = date(2026, 12, 31)

_PL_TYPES = frozenset({"sales", "operating_profit", "net_profit", "ordinary_profit", "eps"})


def main() -> int:
    load_dotenv()
    adapter = JQuantsAdapter()
    if not adapter.configured:
        print(json.dumps({"status": "ERROR", "reason": "JQUANTS_API_KEY not configured"}))
        return 1

    store = RawSnapshotStore(LAB_ROOT / "01_data" / "raw")
    snapshot_prefix = "SNAP_JQS_STD_02_7203"

    def _fetch_or_reuse(snapshot_id: str, fetch_fn):  # noqa: ANN001, ANN202
        # Snapshotは追記のみ(上書き不可、`lib.snapshot.RawSnapshotStore`の設計)。
        # 既に同じsnapshot_idで保存済みなら再Fetch/再Saveせず既存Immutable Snapshotを
        # そのまま再利用する(再実行のたびに同一Historical Rangeを再取得しない)。
        try:
            return store.load("jquants", snapshot_id)
        except FileNotFoundError:
            fetch_result = fetch_fn()
            manifest = store.save(fetch_result, snapshot_id=snapshot_id)
            return manifest, fetch_result.payload

    bars_manifest, bars_payload = _fetch_or_reuse(
        f"{snapshot_prefix}_equity_bars",
        lambda: adapter.fetch_equity_bars(codes=[_ENTITY], start_date=_PRICE_START, end_date=_PRICE_END),
    )
    calendar_manifest, calendar_payload = _fetch_or_reuse(
        f"{snapshot_prefix}_trading_calendar",
        lambda: adapter.fetch_trading_calendar(start_date=_PRICE_START, end_date=_PRICE_END),
    )
    fins_manifest, fins_payload = _fetch_or_reuse(
        f"{snapshot_prefix}_financial_summary",
        lambda: adapter.fetch_financial_statements(codes=[_ENTITY], start_date=_FINS_START, end_date=_FINS_END),
    )
    fins_retrieved_at = datetime.fromisoformat(fins_manifest.retrieved_at)

    envelopes, metrics = parse_financial_summary_payload(fins_payload, retrieved_at=fins_retrieved_at)
    envelopes_by_id = {e.envelope_id: e for e in envelopes}
    metrics_by_id = {m.metric_id: m for m in metrics}

    # DUPLICATE_PERIOD_VINTAGES_OBSERVED(§11): 同一series_id(entity/metric/fiscal_year_target/
    # period/scope/accounting_standard)に複数Versionがあるかを、既存build_revision_histories()の
    # Grouping結果からそのまま観測する(独自のVintage判定Logicを新設しない)。
    key_metrics_for_vintage = [m for m in metrics if m.metric_type in _PL_TYPES and m.value_availability.value == "PRESENT"]
    revision_histories_all = build_revision_histories(envelopes, key_metrics_for_vintage)
    duplicate_period_vintages_observed = any(len(vh.versions) > 1 for vh in revision_histories_all.values())

    eps_metrics = [m for m in metrics if m.metric_type == "eps" and m.value_availability.value == "PRESENT"]
    revision_histories = build_revision_histories(envelopes, eps_metrics)

    actual_eps_series_ids = {
        m.series_id
        for m in metrics
        if m.metric_type == "eps"
        and m.actual_or_forecast == ActualOrForecast.ACTUAL
        and m.period_type == PeriodType.FY
        and m.value_availability.value == "PRESENT"
    }
    if not actual_eps_series_ids:
        print(json.dumps({"status": "ERROR", "reason": "no actual FY EPS series found"}))
        return 1
    actual_eps_revision_histories = {sid: revision_histories[sid] for sid in actual_eps_series_ids}
    # 拡張履歴には会計基準(accounting_standard)分類境界をまたぐ複数series_idが含まれうる
    # (Toyotaの旧DocType('*_Consolidated_US')はparse_financial_summary_payload()が未知の
    # DocTypeとしてaccounting_standard=UNKNOWNへfail closedするため、新basisのseriesとは
    # 別series_idになる、既存Parserの意図した挙動——ここでは書き換えない、§5)。
    # 「Latest Reported FY実績EPS」はSeries横断でcurrent_period_endが最大のVersionを選ぶ
    # (Model Semantics: 複数のFY Denominator RegimeをHistorical Distributionへ混在させる
    # こと自体はLATEST_REPORTED_FY_PERの意味論上正しい、historical_context_builder.py
    # Docstring参照)。この選定Logicは呼び出し側Orchestrationの責務であり
    # (fundamentals_as_of()自体はSeriesごとに独立解決するのみ)、Production Code変更ではない。
    actual_eps_series_count = len(actual_eps_series_ids)

    def _select_latest_reported_fy_actual_eps(as_of: datetime):  # noqa: ANN202
        resolved = fundamentals_as_of(
            actual_eps_revision_histories, as_of, availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT
        )
        candidates = []
        for version in resolved.values():
            if version is None:
                continue
            metric = metrics_by_id[version.source_version_id]
            envelope = envelopes_by_id[metric.envelope_id]
            if envelope.current_period_end is None:
                continue
            candidates.append((envelope.current_period_end, version, metric, envelope))
        if not candidates:
            return None
        candidates.sort(key=lambda c: c[0])
        _period_end, version, metric, envelope = candidates[-1]
        return version, metric, envelope

    raw_bars_full = equity_bars_payload_to_raw_bars(bars_payload)
    corporate_action_events = detect_corporate_action_events_from_equity_bars(bars_payload)

    current_selection = _select_latest_reported_fy_actual_eps(_AS_OF)
    if current_selection is None:
        print(json.dumps({"status": "ERROR", "reason": "current_version could not be resolved as_of target"}))
        return 1
    current_version, current_metric, current_envelope = current_selection
    current_record = build_latest_reported_fy_per(
        entity_code=_ENTITY,
        as_of=_AS_OF,
        raw_bars=raw_bars_full,
        corporate_action_events=corporate_action_events,
        eps_version=current_version,
        eps_metric=current_metric,
        eps_envelope=current_envelope,
    )
    if current_record is None:
        print(json.dumps({"status": "ERROR", "reason": "current_record could not be built"}))
        return 1

    calendar_dates = [date.fromisoformat(str(r["Date"])) for r in calendar_payload]
    calendar = trading_calendar_payload_to_calendar(
        calendar_payload, range_start=min(calendar_dates), range_end=max(calendar_dates), verify_complete_daily_coverage=True
    )
    candidate_months = calendar.completed_month_end_sessions(reference_as_of=_AS_OF)
    attempted_anchor_count = len(candidate_months)
    unavailable_denominator_count = 0
    corporate_action_excluded_count = 0
    historical_records = []
    for session_date in candidate_months:
        anchor_as_of = session_close_at(session_date)
        anchor_selection = _select_latest_reported_fy_actual_eps(anchor_as_of)
        if anchor_selection is None:
            unavailable_denominator_count += 1
            continue
        anchor_version, anchor_metric, anchor_envelope = anchor_selection
        price_bar = select_latest_close_bar(raw_bars_full, as_of=anchor_as_of)
        if price_bar is not None and has_share_basis_action_in_window(
            corporate_action_events, window_start=anchor_envelope.current_period_end, window_end=price_bar.session_date
        ):
            corporate_action_excluded_count += 1
            continue
        historical_record = build_latest_reported_fy_per(
            entity_code=_ENTITY,
            as_of=anchor_as_of,
            raw_bars=raw_bars_full,
            corporate_action_events=corporate_action_events,
            eps_version=anchor_version,
            eps_metric=anchor_metric,
            eps_envelope=anchor_envelope,
        )
        if historical_record is None:
            unavailable_denominator_count += 1
            continue
        historical_records.append(historical_record)

    context_record = build_latest_reported_fy_per_historical_context(
        entity_code=_ENTITY,
        current_reference_as_of=_AS_OF,
        current_record=current_record,
        historical_records=historical_records,
        attempted_anchor_count=attempted_anchor_count,
        excluded_future_anchor_count=0,
        unavailable_denominator_count=unavailable_denominator_count,
        corporate_action_excluded_count=corporate_action_excluded_count,
        minimum_sample_count=12,
    )

    disclosure_dates = [e.disclosure_date for e in envelopes if e.disclosure_date is not None]

    result: dict[str, object] = {
        "status": "BUILT" if context_record is not None else "BELOW_MINIMUM_SAMPLE",
        "as_of": _AS_OF.isoformat(),
        "snapshots": {
            "equity_bars": {
                "snapshot_id": bars_manifest.snapshot_id,
                "content_hash": bars_manifest.content_hash,
                "record_count": bars_manifest.record_count,
            },
            "trading_calendar": {
                "snapshot_id": calendar_manifest.snapshot_id,
                "content_hash": calendar_manifest.content_hash,
                "record_count": calendar_manifest.record_count,
            },
            "financial_summary": {
                "snapshot_id": fins_manifest.snapshot_id,
                "content_hash": fins_manifest.content_hash,
                "record_count": fins_manifest.record_count,
            },
        },
        "raw_history_start_price": min(b.session_date for b in raw_bars_full).isoformat(),
        "raw_history_start_financials": (min(disclosure_dates).isoformat() if disclosure_dates else None),
        "attempted_anchor_count": attempted_anchor_count,
        "excluded_future_anchor_count": 0,
        "unavailable_denominator_count": unavailable_denominator_count,
        "corporate_action_excluded_count": corporate_action_excluded_count,
        "sample_count": len(historical_records),
        "duplicate_period_vintages_observed": duplicate_period_vintages_observed,
        "revision_relationship_resolved": False,  # build_revision_histories()の設計上常にFalse(supersedes_version_id=None)
        "actual_eps_series_count": actual_eps_series_count,
    }
    if context_record is not None:
        result.update(
            {
                "historical_sample_start_as_of": context_record.historical_sample_start_as_of.isoformat(),
                "historical_sample_end_as_of": context_record.historical_sample_end_as_of.isoformat(),
                "historical_min": str(context_record.historical_min),
                "historical_median": str(context_record.historical_median),
                "historical_max": str(context_record.historical_max),
                "current_per": str(context_record.current_per),
                "current_percentile": str(context_record.current_percentile),
                "current_minus_historical_median": str(context_record.current_minus_historical_median),
                "context_status": context_record.context_status.value,
                "denominator_regimes": [
                    {"fiscal_period_end": r.fiscal_period_end.isoformat(), "observation_count": r.observation_count}
                    for r in context_record.denominator_regimes
                ],
                "distinct_denominator_regime_count": context_record.distinct_denominator_regime_count,
            }
        )

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
