"""Stage 3.15 Closure Reproducible Acceptance Harness(Stage 3.15.3、D0092)。

D0090/D0091のReal 7203 Acceptanceは、これまでRepo外のScratch Directoryで
しか再現できなかった(最大のRepo-verifiability Gap)。このScriptは、
既存Local Snapshotが存在する環境であればNetwork Fetchなしに再現できる、
正式なRead-only Acceptance Harnessとしてリポジトリへcommitする。

**Scratchからのlogic Copy-Pasteは行わない**: 既存Production API
(Parser・A-Path Fundamentals Converter・Valuation Builder・v2 Evidence
Converter・Historical Context Builder・EvidenceRegistry・EvidencePacket
Registry・ProvenanceStore・ResearchArtifactRegistry・`lib.valuation.
provenance`のUpstream Provenance Helper・`build_research_artifact()`)
を呼ぶ薄いOrchestrationのみで構成する。

使い方:
    python scripts/verify_stage3_15_7203_closure.py --mode build \
        --snapshot-root Japanese_Equity_Lab/01_data/raw/local_snapshot_input \
        --output-dir <isolated temp dir>
    python scripts/verify_stage3_15_7203_closure.py --mode verify \
        --output-dir <同じisolated temp dir、別Processとして実行することを推奨>

`--mode build`(Process A相当)がConstruction + Persistenceを行い、
`--mode verify`(Process B相当)が別Python Processとして起動された場合に
真のFresh Process境界での再検証となる(呼び出し側の責務、このScript自体は
2回のInvocationを強制しない)。

**制約**: Network Fetchなし・新規Provider禁止・Raw Snapshot/`02_company_
research/`への書き込みなし・出力はTemp Directoryのみ・as_ofは
2024-11-15T15:00 JST固定・H0001 Locked Testには一切触れない。
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parent.parent
LAB_ROOT = REPO_ROOT / "Japanese_Equity_Lab"
sys.path.insert(0, str(LAB_ROOT))

from lib.data_sources.convert import (  # noqa: E402
    detect_corporate_action_events_from_equity_bars,
    equity_bars_payload_to_raw_bars,
    trading_calendar_payload_to_calendar,
)
from lib.data_sources.local_snapshot import LocalSnapshotAdapter  # noqa: E402
from lib.evidence.model import AvailabilitySemantics, EvidenceRecord, EvidenceRelation  # noqa: E402
from lib.evidence.research_artifact import (  # noqa: E402
    ConfidenceLevel,
    DataGap,
    DataGapStatus,
    NarrativeCase,
    ResearchConclusion,
    build_research_artifact,
)
from lib.evidence.retrieval import ResearchQuestion  # noqa: E402
from lib.fundamentals.evidence import (  # noqa: E402
    financial_quality_metric_to_evidence_market_public_at,
    guidance_metric_to_evidence_market_public_at,
    source_version_to_evidence_market_public_at,
)
from lib.fundamentals.model import ActualOrForecast, PeriodType  # noqa: E402
from lib.fundamentals.normalize import build_revision_histories, parse_financial_summary_payload  # noqa: E402
from lib.fundamentals.same_period_yoy_builder import build_same_period_yoy_change, select_same_period_yoy_candidates  # noqa: E402
from lib.fundamentals.same_period_yoy_evidence import same_period_yoy_change_to_evidence  # noqa: E402
from lib.fundamentals.view import fundamentals_as_of  # noqa: E402
from lib.market_calendar import session_close_at  # noqa: E402
from lib.positioning.derived.price_derived import build_turnover_value_records, build_volume_moving_average_records  # noqa: E402
from lib.registry.evidence_packet_registry import EvidencePacketRegistry  # noqa: E402
from lib.registry.evidence_registry import EvidenceRegistry  # noqa: E402
from lib.registry.provenance import ProvenanceStore  # noqa: E402
from lib.registry.research_artifact_registry import ResearchArtifactRegistry  # noqa: E402
from lib.schemas.price_data import apply_split_adjustments  # noqa: E402
from lib.sources.catalog import SourceAuthorityClass  # noqa: E402
from lib.valuation.builder import (  # noqa: E402
    build_latest_reported_fy_per,
    has_share_basis_action_in_window,
    select_latest_close_bar,
)
from lib.valuation.current_fy_forecast_builder import (  # noqa: E402
    build_current_fy_company_forecast_per,
    select_current_fy_company_forecast_eps_candidate,
)
from lib.valuation.evidence import (  # noqa: E402
    current_fy_company_forecast_per_to_evidence,
    latest_reported_fy_per_to_evidence_v2,
)
from lib.valuation.historical_context_builder import build_latest_reported_fy_per_historical_context  # noqa: E402
from lib.valuation.historical_context_evidence import (  # noqa: E402
    latest_reported_fy_per_historical_context_to_evidence,
    verify_historical_context_provenance,
)
from lib.valuation.provenance import register_historical_context_provenance_bundle  # noqa: E402

_JST = ZoneInfo("Asia/Tokyo")
_ENTITY = "7203"
_AS_OF = datetime(2024, 11, 15, 15, 0, tzinfo=_JST)
_AUTH = SourceAuthorityClass.PRIMARY_OFFICIAL
_ORIG = "JQUANTS_SOURCE_DATA"
_DELIV = "JQUANTS"

_PL_TYPES = frozenset({"sales", "operating_profit", "net_profit", "ordinary_profit", "eps"})
_CASHFLOW_TYPES = frozenset({"cash_flow_from_operations", "cash_flow_from_investing", "cash_flow_from_financing"})
_BALANCE_TYPES = frozenset({"total_assets", "provider_reported_sheq", "provider_reported_eqar"})
_GUIDANCE_TYPES = frozenset(
    {
        "sales_current_year_forecast",
        "operating_profit_current_year_forecast",
        "net_profit_current_year_forecast",
        "ordinary_profit_current_year_forecast",
        "eps_current_year_forecast",
    }
)
_ALL_FUNDAMENTAL_TYPES = _PL_TYPES | _CASHFLOW_TYPES | _BALANCE_TYPES | _GUIDANCE_TYPES
_YOY_UNDERLYING_TYPES = ("sales", "operating_profit", "net_profit", "eps")

_EXPECTED_HISTORICAL_MIN = Decimal("6.947860304968027545499262174")
_EXPECTED_HISTORICAL_MEDIAN = Decimal("10.23607659698874433562344686")
_EXPECTED_HISTORICAL_MAX = Decimal("21.12887947846436730372764250")
_EXPECTED_CURRENT_PERCENTILE = Decimal("3.333333333333333333333333333")
_EXPECTED_CURRENT_MINUS_MEDIAN = Decimal("-2.950729272290706405908192993")
_EXPECTED_CURRENT_PER = Decimal("7.285347324698037929715253867")

# Stage 3.15 Acceptance Contractとしてのみ使用するExpected Test Values(Stage 3.15.4、
# D0093)。Production Business Logic(Historical Context Builder等)へこれらの値を
# 埋め込むことはしない——あくまでこのHarness自身のVerify-Side Assertion専用。
_EXPECTED_LINEAGE_ONLY_HISTORICAL_PER_COUNT = 30
_EXPECTED_TOTAL_UNIQUE_EVIDENCE_NODES = 107
_EXPECTED_REGIME_OBSERVATION_COUNTS: dict[date, int] = {
    date(2022, 3, 31): 12,
    date(2023, 3, 31): 12,
    date(2024, 3, 31): 6,
}


def _build_and_persist(*, snapshot_root: Path, output_dir: Path) -> dict[str, object]:
    adapter = LocalSnapshotAdapter(snapshot_root)

    fins_result = adapter.fetch_financial_statements(codes=[_ENTITY], start_date=date(2020, 1, 1), end_date=date(2026, 12, 31))
    envelopes, metrics = parse_financial_summary_payload(fins_result.payload, retrieved_at=fins_result.retrieved_at)
    key_metrics = [m for m in metrics if m.metric_type in _ALL_FUNDAMENTAL_TYPES and m.value_availability.value == "PRESENT"]
    revision_histories = build_revision_histories(envelopes, key_metrics)
    envelopes_by_id = {e.envelope_id: e for e in envelopes}
    metrics_by_id = {m.metric_id: m for m in metrics}
    selected = fundamentals_as_of(revision_histories, _AS_OF, availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT)

    pl_evidence: list[EvidenceRecord] = []
    cashflow_evidence: list[EvidenceRecord] = []
    balance_evidence: list[EvidenceRecord] = []
    guidance_evidence: list[EvidenceRecord] = []
    for _series_id, version in selected.items():
        if version is None:
            continue
        metric = metrics_by_id[version.source_version_id]
        envelope = envelopes_by_id[metric.envelope_id]
        if metric.metric_type in _PL_TYPES:
            pl_evidence.append(source_version_to_evidence_market_public_at(version, entity_code=_ENTITY))
        elif metric.metric_type in _CASHFLOW_TYPES:
            cashflow_evidence.append(
                financial_quality_metric_to_evidence_market_public_at(
                    version, metric=metric, envelope=envelope, entity_code=_ENTITY
                )
            )
        elif metric.metric_type in _BALANCE_TYPES:
            balance_evidence.append(
                financial_quality_metric_to_evidence_market_public_at(
                    version, metric=metric, envelope=envelope, entity_code=_ENTITY
                )
            )
        elif metric.metric_type in _GUIDANCE_TYPES:
            guidance_evidence.append(
                guidance_metric_to_evidence_market_public_at(version, metric=metric, envelope=envelope, entity_code=_ENTITY)
            )

    bars_result = adapter.fetch_equity_bars(codes=[_ENTITY], start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))
    raw_bars_2024 = equity_bars_payload_to_raw_bars(bars_result.payload)
    adjusted_bars_2024 = apply_split_adjustments(raw_bars_2024, [])
    sessions_on_or_before = sorted({b.session_date for b in raw_bars_2024 if b.session_date <= _AS_OF.date()})
    window_sessions = set(sessions_on_or_before[-10:])
    turnover_records = [
        r
        for r in build_turnover_value_records(raw_bars_2024, retrieved_at=bars_result.retrieved_at)
        if r.observation_end in window_sessions
    ]
    volma_records = [
        r
        for r in build_volume_moving_average_records(adjusted_bars_2024, window=20, retrieved_at=bars_result.retrieved_at)
        if r.observation_end in window_sessions
    ]
    from lib.evidence.model import DataLayer
    from lib.evidence.research_artifact import price_derived_record_to_evidence

    positioning_built = [
        price_derived_record_to_evidence(
            rec, layer=DataLayer.DERIVED, source_authority_class=_AUTH, originating_source=_ORIG, delivery_provider=_DELIV
        )
        for rec in [*turnover_records, *volma_records]
        if rec.value_availability.value == "PRESENT"
    ]

    yoy_evidence: list[EvidenceRecord] = []
    for underlying in _YOY_UNDERLYING_TYPES:
        candidates = []
        for m in metrics:
            if m.metric_type != underlying or m.value_availability.value != "PRESENT":
                continue
            vh = revision_histories.get(m.series_id)
            env = envelopes_by_id.get(m.envelope_id)
            if vh is None or env is None:
                continue
            for ver in vh.versions:
                if ver.source_version_id == m.metric_id:
                    candidates.append((ver, m, env))
        pair = select_same_period_yoy_candidates(candidates, entity_code=_ENTITY, as_of=_AS_OF, underlying_metric_type=underlying)
        if pair is None:
            continue
        (cv, cm, ce), (pv, pm, pe) = pair
        yoy_record = build_same_period_yoy_change(
            entity_code=_ENTITY,
            as_of=_AS_OF,
            underlying_metric_type=underlying,
            current_version=cv,
            current_metric=cm,
            current_envelope=ce,
            prior_version=pv,
            prior_metric=pm,
            prior_envelope=pe,
        )
        if yoy_record is not None:
            yoy_evidence.append(
                same_period_yoy_change_to_evidence(
                    yoy_record, source_authority_class=_AUTH, originating_source=_ORIG, delivery_provider=_DELIV
                )
            )

    price_bars_full = adapter.fetch_equity_bars(codes=[_ENTITY], start_date=date(2020, 1, 1), end_date=date(2026, 12, 31))
    raw_bars_full = equity_bars_payload_to_raw_bars(price_bars_full.payload)
    corporate_action_events = detect_corporate_action_events_from_equity_bars(price_bars_full.payload)

    forecast_candidates = []
    for m in metrics:
        if m.metric_type != "eps_current_year_forecast" or m.value_availability.value != "PRESENT":
            continue
        vh = revision_histories.get(m.series_id)
        env = envelopes_by_id.get(m.envelope_id)
        if vh is None or env is None:
            continue
        for ver in vh.versions:
            if ver.source_version_id == m.metric_id:
                forecast_candidates.append((ver, m, env))
    forecast_pick = select_current_fy_company_forecast_eps_candidate(forecast_candidates, entity_code=_ENTITY, as_of=_AS_OF)
    assert forecast_pick is not None, "Current FY Company Forecast EPS candidate not found"
    fcv, fcm, fce = forecast_pick
    forecast_per_record = build_current_fy_company_forecast_per(
        entity_code=_ENTITY,
        as_of=_AS_OF,
        raw_bars=raw_bars_full,
        corporate_action_events=corporate_action_events,
        guidance_version=fcv,
        guidance_metric=fcm,
        guidance_envelope=fce,
    )
    assert forecast_per_record is not None
    forecast_per_evidence = current_fy_company_forecast_per_to_evidence(
        forecast_per_record, source_authority_class=_AUTH, originating_source=_ORIG, delivery_provider=_DELIV
    )

    actual_eps_series_ids = {
        m.series_id
        for m in metrics
        if m.metric_type == "eps"
        and m.actual_or_forecast == ActualOrForecast.ACTUAL
        and m.period_type == PeriodType.FY
        and m.value_availability.value == "PRESENT"
    }
    assert len(actual_eps_series_ids) == 1
    (actual_eps_series_id,) = actual_eps_series_ids
    current_eps_version = fundamentals_as_of(
        {actual_eps_series_id: revision_histories[actual_eps_series_id]},
        _AS_OF,
        availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT,
    )[actual_eps_series_id]
    assert current_eps_version is not None
    current_eps_metric = metrics_by_id[current_eps_version.source_version_id]
    current_eps_envelope = envelopes_by_id[current_eps_metric.envelope_id]
    current_record = build_latest_reported_fy_per(
        entity_code=_ENTITY,
        as_of=_AS_OF,
        raw_bars=raw_bars_full,
        corporate_action_events=corporate_action_events,
        eps_version=current_eps_version,
        eps_metric=current_eps_metric,
        eps_envelope=current_eps_envelope,
    )
    assert current_record is not None
    current_actual_per_evidence = latest_reported_fy_per_to_evidence_v2(
        current_record, source_authority_class=_AUTH, originating_source=_ORIG, delivery_provider=_DELIV
    )

    calendar_result = adapter.fetch_trading_calendar(start_date=date(2020, 1, 1), end_date=date(2026, 12, 31))
    calendar_dates = [date.fromisoformat(str(r["Date"])) for r in calendar_result.payload]
    calendar = trading_calendar_payload_to_calendar(
        calendar_result.payload,
        range_start=min(calendar_dates),
        range_end=max(calendar_dates),
        verify_complete_daily_coverage=True,
    )
    candidate_months = calendar.completed_month_end_sessions(reference_as_of=_AS_OF)
    attempted_anchor_count = len(candidate_months)
    unavailable_denominator_count = 0
    corporate_action_excluded_count = 0
    historical_records = []
    for session_date in candidate_months:
        anchor_as_of = session_close_at(session_date)
        anchor_version = fundamentals_as_of(
            {actual_eps_series_id: revision_histories[actual_eps_series_id]},
            anchor_as_of,
            availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT,
        )[actual_eps_series_id]
        if anchor_version is None:
            unavailable_denominator_count += 1
            continue
        anchor_metric = metrics_by_id[anchor_version.source_version_id]
        anchor_envelope = envelopes_by_id[anchor_metric.envelope_id]
        if anchor_envelope.current_period_end is None:
            unavailable_denominator_count += 1
            continue
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
    assert context_record is not None
    context_evidence = latest_reported_fy_per_historical_context_to_evidence(
        context_record, source_authority_class=_AUTH, originating_source=_ORIG, delivery_provider=_DELIV
    )
    historical_evidences = [
        latest_reported_fy_per_to_evidence_v2(r, source_authority_class=_AUTH, originating_source=_ORIG, delivery_provider=_DELIV)
        for r in historical_records
    ]
    assert current_actual_per_evidence.evidence_id == context_record.current_per_observation_id

    artifact_evidence: list[EvidenceRecord] = [
        *pl_evidence,
        *cashflow_evidence,
        *balance_evidence,
        *guidance_evidence,
        *positioning_built,
        forecast_per_evidence,
        current_actual_per_evidence,
        *yoy_evidence,
        context_evidence,
    ]
    usable_at_as_of = [e for e in artifact_evidence if e.is_usable_at(_AS_OF)]
    relations = {e.evidence_id: EvidenceRelation.NEUTRAL for e in usable_at_as_of}
    base_refs = tuple(e.evidence_id for e in usable_at_as_of if e.evidence_id != context_evidence.evidence_id)

    data_gaps = [
        DataGap(
            topic=f"Historical Valuation Context Coverage ({_ENTITY}, LATEST_REPORTED_FY_PER_HISTORICAL_CONTEXT)",
            status=DataGapStatus.MISSING,
            note="Historical Contextは存在するが約2.4年のみで、より長いHistoryが不足している。",
        ),
        DataGap(
            topic="J-Quants Financial Summary Source Vintage Completeness",
            status=DataGapStatus.UNVERIFIED,
            note="訂正前値が必ずHistorical Rowとして保持されるかは公式仕様から確認できていない。",
        ),
    ]

    artifact, packet = build_research_artifact(
        artifact_id="ART_STAGE3_15_3_7203_20241115_A_V1",
        entity_code=_ENTITY,
        question=ResearchQuestion(
            question_id="RQ_STAGE3_15_3_7203_0001",
            text="Stage 3.15 Closure Reproducible Acceptance",
            as_of=_AS_OF,
            related_codes=(_ENTITY,),
        ),
        evidence_pool=usable_at_as_of,
        relations=relations,
        bull_case=NarrativeCase(summary="方向性のあるBull Caseは主張しない(Research != Decision)。"),
        base_case=NarrativeCase(summary="Acceptance用の観測Evidence群。", supporting_evidence_ids=base_refs),
        bear_case=NarrativeCase(summary="方向性のあるBear Caseも主張しない(同上)。"),
        data_confidence=ConfidenceLevel.LOW,
        evidence_confidence=ConfidenceLevel.MEDIUM,
        research_confidence=ConfidenceLevel.LOW,
        conclusion=ResearchConclusion.INCONCLUSIVE,
        conclusion_rationale="Stage 3.15 Closure Reproducible Acceptance Harness(D0092)。",
        data_gaps=data_gaps,
        fundamentals_availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    evidence_registry = EvidenceRegistry(output_dir / "evidence_registry.jsonl")
    for e in usable_at_as_of:
        evidence_registry.register(e)
    for e in historical_evidences:
        evidence_registry.register(e)

    provenance_store = ProvenanceStore(output_dir / "provenance.jsonl")
    register_historical_context_provenance_bundle(
        context_record=context_record,
        context_evidence=context_evidence,
        current_record=current_record,
        current_evidence=current_actual_per_evidence,
        historical_records=historical_records,
        historical_evidences=historical_evidences,
        evidence_registry=evidence_registry,
        provenance_store=provenance_store,
    )

    packet_registry = EvidencePacketRegistry(output_dir / "packets.jsonl")
    packet_registry.record(packet)

    artifact_registry = ResearchArtifactRegistry(output_dir / "research_artifact.jsonl")
    artifact_registry.record(artifact)

    return {"status": "BUILT", "artifact_id": artifact.artifact_id}


def _verify(*, snapshot_root: Path, output_dir: Path) -> dict[str, object]:
    failures: list[str] = []

    def check(label: str, condition: bool) -> None:
        if not condition:
            failures.append(label)

    evidence_registry = EvidenceRegistry(output_dir / "evidence_registry.jsonl")
    provenance_store = ProvenanceStore(output_dir / "provenance.jsonl")
    packet_registry = EvidencePacketRegistry(output_dir / "packets.jsonl")
    artifact_registry = ResearchArtifactRegistry(output_dir / "research_artifact.jsonl")

    artifacts = artifact_registry.all()
    check("exactly_1_artifact", len(artifacts) == 1)
    artifact = artifacts[0]

    artifact_included_evidence_count = len(artifact.included_evidence_ids)
    check("artifact_included_evidence_count_77", artifact_included_evidence_count == 77)

    all_evidence = evidence_registry.all()
    total_unique_evidence_nodes = len(all_evidence)
    # Stage 3.15.4(D0093): 実測Set(EvidenceRegistry.all())から求めたUnique Node数を
    # Acceptance Contract上のExpected値(107、Production Magic Constantではない)と
    # 実際にcheck()する(以前はSummaryへ書き出すのみだった、Codex Finding)。
    check("total_unique_evidence_nodes", total_unique_evidence_nodes == _EXPECTED_TOTAL_UNIQUE_EVIDENCE_NODES)
    resolved_included = sum(1 for eid in artifact.included_evidence_ids if evidence_registry.get(eid) is not None)
    check("all_included_evidence_resolve", resolved_included == artifact_included_evidence_count)

    from lib.valuation.model import SOURCE_ID_LATEST_REPORTED_FY_PER_HISTORICAL_CONTEXT

    context_candidates = [e for e in all_evidence if e.source.source_type == SOURCE_ID_LATEST_REPORTED_FY_PER_HISTORICAL_CONTEXT]
    check("exactly_1_context_evidence", len(context_candidates) == 1)
    context_evidence = context_candidates[0]
    check("context_evidence_in_included", context_evidence.evidence_id in artifact.included_evidence_ids)

    context_to_per_links = provenance_store.parents_of("valuation_evidence", context_evidence.evidence_id)
    context_to_per_edges = len(context_to_per_links)
    check("context_to_per_edges_31", context_to_per_edges == 31)

    per_ids = [link.from_id for link in context_to_per_links]
    lineage_only_ids = [pid for pid in per_ids if pid not in set(artifact.included_evidence_ids)]
    lineage_only_historical_per = len(lineage_only_ids)
    # Stage 3.15.4(D0093): 従来はSummaryへ書き出すのみでPASS/FAIL判定に使っていなかった
    # (Codex Finding、Acceptance Harness Assertion Gap)。ここで実際にcheck()する。
    check("lineage_only_historical_per_count", lineage_only_historical_per == _EXPECTED_LINEAGE_ONLY_HISTORICAL_PER_COUNT)

    from lib.valuation.model import SOURCE_ID as PER_SOURCE_ID  # noqa: N811

    current_candidates = [
        pid
        for pid in per_ids
        if pid in set(artifact.included_evidence_ids)
        and (ev := evidence_registry.get(pid)) is not None
        and ev.source.source_type == PER_SOURCE_ID
    ]
    check("exactly_1_current_per_in_included", len(current_candidates) == 1)
    current_per_artifact_id = current_candidates[0] if current_candidates else None

    price_edges = 0
    eps_edges = 0
    price_raw_resolved = 0
    eps_raw_resolved = 0
    adapter = LocalSnapshotAdapter(snapshot_root)
    fins_result = adapter.fetch_financial_statements(codes=[_ENTITY], start_date=date(2020, 1, 1), end_date=date(2026, 12, 31))
    _envelopes, metrics = parse_financial_summary_payload(fins_result.payload, retrieved_at=fins_result.retrieved_at)
    fins_metric_ids = {m.metric_id for m in metrics}
    for per_id in per_ids:
        parents = provenance_store.parents_of("valuation_evidence", per_id)
        price_links = [link for link in parents if link.from_type == "price_bar"]
        eps_links = [link for link in parents if link.from_type == "fundamental_source_version"]
        if len(price_links) == 1:
            price_edges += 1
            entity_code, price_date_str = price_links[0].from_id.split(":")
            bars = adapter.fetch_equity_bars(
                codes=[entity_code], start_date=date.fromisoformat(price_date_str), end_date=date.fromisoformat(price_date_str)
            )
            if any(str(row.get("Date")) == price_date_str for row in bars.payload):
                price_raw_resolved += 1
        if len(eps_links) == 1:
            eps_edges += 1
            if eps_links[0].from_id in fins_metric_ids:
                eps_raw_resolved += 1

    check("per_to_price_edges_31", price_edges == 31)
    check("per_to_eps_edges_31", eps_edges == 31)
    check("price_raw_resolved_31", price_raw_resolved == 31)
    check("eps_raw_resolved_31", eps_raw_resolved == 31)

    v1_current_present = any(ev.source.source_type == PER_SOURCE_ID and "_V2_" not in ev.evidence_id for ev in all_evidence)
    check("v1_current_absent", v1_current_present is False)

    packet = packet_registry.get(artifact.evidence_packet_id)
    check("packet_resolves", packet is not None)
    context_relation = None
    relation_assignments_tracked = False
    if packet is not None:
        relation_assignments_tracked = packet.relation_assignments_tracked
        by_id = {a.evidence_id: a.relation for a in packet.relation_assignments}
        context_relation = by_id.get(context_evidence.evidence_id)
    check("relation_assignments_tracked_true", relation_assignments_tracked is True)
    check("context_relation_neutral", context_relation == EvidenceRelation.NEUTRAL)

    historical_gap = next((g for g in artifact.data_gaps if "Historical Valuation Context Coverage" in g.topic), None)
    vintage_gap = next((g for g in artifact.data_gaps if "Source Vintage" in g.topic), None)
    check("historical_coverage_gap_present", historical_gap is not None and historical_gap.status == DataGapStatus.MISSING)
    check("source_vintage_gap_present", vintage_gap is not None and vintage_gap.status == DataGapStatus.UNVERIFIED)

    check("data_confidence_low", artifact.data_confidence == ConfidenceLevel.LOW)
    check("evidence_confidence_medium", artifact.evidence_confidence == ConfidenceLevel.MEDIUM)
    check("research_confidence_low", artifact.research_confidence == ConfidenceLevel.LOW)
    check("conclusion_inconclusive", artifact.conclusion == ResearchConclusion.INCONCLUSIVE)

    # Historical Context本体をRead-only Snapshotから再導出し、verify_historical_context_provenance()本体を実行する。
    envelopes, metrics2 = parse_financial_summary_payload(fins_result.payload, retrieved_at=fins_result.retrieved_at)
    envelopes_by_id = {e.envelope_id: e for e in envelopes}
    metrics_by_id = {m.metric_id: m for m in metrics2}
    actual_eps_series_ids = {
        m.series_id
        for m in metrics2
        if m.metric_type == "eps"
        and m.actual_or_forecast == ActualOrForecast.ACTUAL
        and m.period_type == PeriodType.FY
        and m.value_availability.value == "PRESENT"
    }
    (actual_eps_series_id,) = actual_eps_series_ids
    eps_metrics = [m for m in metrics2 if m.series_id == actual_eps_series_id and m.value_availability.value == "PRESENT"]
    revision_histories = build_revision_histories(envelopes, eps_metrics)

    price_bars_full = adapter.fetch_equity_bars(codes=[_ENTITY], start_date=date(2020, 1, 1), end_date=date(2026, 12, 31))
    raw_bars_full = equity_bars_payload_to_raw_bars(price_bars_full.payload)
    corporate_action_events = detect_corporate_action_events_from_equity_bars(price_bars_full.payload)
    calendar_result = adapter.fetch_trading_calendar(start_date=date(2020, 1, 1), end_date=date(2026, 12, 31))
    calendar_dates = [date.fromisoformat(str(r["Date"])) for r in calendar_result.payload]
    calendar = trading_calendar_payload_to_calendar(
        calendar_result.payload,
        range_start=min(calendar_dates),
        range_end=max(calendar_dates),
        verify_complete_daily_coverage=True,
    )
    candidate_months = calendar.completed_month_end_sessions(reference_as_of=_AS_OF)
    historical_records = []
    unavailable = 0
    ca_excluded = 0
    for session_date in candidate_months:
        anchor_as_of = session_close_at(session_date)
        anchor_version = fundamentals_as_of(
            revision_histories, anchor_as_of, availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT
        )[actual_eps_series_id]
        if anchor_version is None:
            unavailable += 1
            continue
        anchor_metric = metrics_by_id[anchor_version.source_version_id]
        anchor_envelope = envelopes_by_id[anchor_metric.envelope_id]
        if anchor_envelope.current_period_end is None:
            unavailable += 1
            continue
        price_bar = select_latest_close_bar(raw_bars_full, as_of=anchor_as_of)
        if price_bar is not None and has_share_basis_action_in_window(
            corporate_action_events, window_start=anchor_envelope.current_period_end, window_end=price_bar.session_date
        ):
            ca_excluded += 1
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
            unavailable += 1
            continue
        historical_records.append(historical_record)

    current_version = fundamentals_as_of(
        revision_histories, _AS_OF, availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT
    )[actual_eps_series_id]
    if current_version is None:
        raise SystemExit("current_version(FY Actual EPS)がas_of時点で解決できませんでした(fail closed)")
    current_metric = metrics_by_id[current_version.source_version_id]
    current_envelope = envelopes_by_id[current_metric.envelope_id]
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
        raise SystemExit("current_record(Current Actual PER)が解決できませんでした(fail closed)")
    rederived_context = build_latest_reported_fy_per_historical_context(
        entity_code=_ENTITY,
        current_reference_as_of=_AS_OF,
        current_record=current_record,
        historical_records=historical_records,
        attempted_anchor_count=len(candidate_months),
        excluded_future_anchor_count=0,
        unavailable_denominator_count=unavailable,
        corporate_action_excluded_count=ca_excluded,
        minimum_sample_count=12,
    )
    check("rederived_context_not_none", rederived_context is not None)
    historical_sample_count = rederived_context.sample_count if rederived_context is not None else None
    check("historical_sample_count_30", historical_sample_count == 30)

    numeric_regression_ok = False
    if rederived_context is not None:
        numeric_regression_ok = (
            rederived_context.historical_min == _EXPECTED_HISTORICAL_MIN
            and rederived_context.historical_median == _EXPECTED_HISTORICAL_MEDIAN
            and rederived_context.historical_max == _EXPECTED_HISTORICAL_MAX
            and rederived_context.current_percentile == _EXPECTED_CURRENT_PERCENTILE
            and rederived_context.current_minus_historical_median == _EXPECTED_CURRENT_MINUS_MEDIAN
        )
    check("numeric_zero_regression", numeric_regression_ok)

    # Stage 3.15.4(D0093): 以下3件はSummaryへ書き出すだけでPASS/FAIL判定に使っていな
    # かった(Codex FINAL Stage 3.15 Acceptance Audit、NEEDS_TINY_FIXの唯一のFinding)。
    # Summary値の自己比較ではなく、Fresh Processでreload/rederiveした実測値同士を
    # 比較する。Production Semantics(Historical Context Builder/Model)は無変更。
    regime_counts: dict[date, int] | None = None
    if rederived_context is not None:
        # Current PER Shared Node: Artifact内のCurrent PER Evidence IDと、
        # Fresh Processで再導出したContextのcurrent_per_observation_idが厳密に
        # 同一Evidence IDであることを検証する(§15要件)。
        check("current_per_shared_node", current_per_artifact_id == rederived_context.current_per_observation_id)

        # Exact Current PER: Decimal同士のExact Comparison(floatへ変換しない)。
        check("current_per_exact_regression", rederived_context.current_per == _EXPECTED_CURRENT_PER)

        # Regime Observation Counts: Production Context Recordが保持する型付き
        # `denominator_regimes`(`DenominatorRegimeSummary.fiscal_period_end`/
        # `.observation_count`)から直接算出する(文字列Parseや推測はしない)。
        regime_counts = {r.fiscal_period_end: r.observation_count for r in rederived_context.denominator_regimes}
        check("regime_observation_counts_12_12_6", regime_counts == _EXPECTED_REGIME_OBSERVATION_COUNTS)
    else:
        check("current_per_shared_node", False)
        check("current_per_exact_regression", False)
        check("regime_observation_counts_12_12_6", False)

    if rederived_context is not None:
        try:
            verify_historical_context_provenance(
                rederived_context,
                context_evidence_id=context_evidence.evidence_id,
                provenance_store=provenance_store,
                evidence_registry=evidence_registry,
            )
            verify_ok = True
        except ValueError:
            verify_ok = False
        check("verify_historical_context_provenance_pass", verify_ok)

    result: dict[str, object] = {
        "status": "PASS" if not failures else "FAIL",
        "artifact_evidence_count": artifact_included_evidence_count,
        "lineage_only_count": lineage_only_historical_per,
        "unique_evidence_count": total_unique_evidence_nodes,
        "context_to_per_edges": context_to_per_edges,
        "per_to_price_edges": price_edges,
        "per_to_eps_edges": eps_edges,
        "price_raw_resolved": price_raw_resolved,
        "eps_raw_resolved": eps_raw_resolved,
        "context_relation": context_relation.value if context_relation is not None else None,
        "relation_assignments_tracked": relation_assignments_tracked,
        "current_per_artifact_id": current_per_artifact_id,
        "context_current_parent_id": rederived_context.current_per_observation_id if rederived_context is not None else None,
        "current_per_shared_node": current_per_artifact_id == rederived_context.current_per_observation_id
        if rederived_context is not None
        else False,
        "v1_current_present": v1_current_present,
        "historical_sample_count": historical_sample_count,
        "current_per": str(rederived_context.current_per) if rederived_context is not None else None,
        "regime_counts": {d.isoformat(): c for d, c in regime_counts.items()} if regime_counts is not None else None,
        "numeric_regression": "ZERO_DIFF" if numeric_regression_ok else "MISMATCH",
        "confidence": {
            "data": artifact.data_confidence.value,
            "evidence": artifact.evidence_confidence.value,
            "research": artifact.research_confidence.value,
        },
        "conclusion": artifact.conclusion.value,
        "failures": failures,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", choices=["build", "verify"], required=True)
    parser.add_argument("--snapshot-root", type=Path, default=LAB_ROOT / "01_data" / "raw" / "local_snapshot_input")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(tempfile.gettempdir()) / "stage3_15_closure_acceptance" / "isolated_runtime",
    )
    args = parser.parse_args()

    if args.mode == "build":
        result = _build_and_persist(snapshot_root=args.snapshot_root, output_dir=args.output_dir)
    else:
        result = _verify(snapshot_root=args.snapshot_root, output_dir=args.output_dir)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("status") in ("PASS", "BUILT"):
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
