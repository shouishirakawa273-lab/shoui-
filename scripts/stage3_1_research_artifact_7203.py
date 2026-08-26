"""Stage 3.1: Real-Data Research Acceptance再試行(D0072/D0073 Follow-up)。

D0073は「実データ0件」でBLOCKEDと結論したが、これは当時のセッション
(エフェメラルなクラウドコンテナ)固有の状態だった。ユーザーのローカルPC上
には既に`01_data/raw/local_snapshot_input/`(.gitignore対象)へ
2026-08-16に取得済みの実J-Quants Local Snapshot(7203/6758/8056/3626、
Financial Summary + Daily Bars)が存在する。このScriptはその既存Snapshotだけ
を使い、新規API呼び出しは一切行わずにStage 3 v1(`build_research_artifact()`、
D0072)を1社(7203)+明示的as_ofでEnd-to-Endに通す。

**Historical PIT Safety(このRoundの核心制約)**: 「実データである」ことと
「その2024年当時のas_ofで安全に使えるEvidenceである」ことは別軸である。
`retrieved_at=2026-08-16`のSnapshotを、2024年当時にこのLabが実際に保持
していたかのように装わない。既存の2つのPIT機構をそのまま使い、一切上書き
しない:

- Fundamentals(`lib.fundamentals.evidence.disclosure_metric_to_evidence()`):
  `available_at = envelope.retrieved_at`を常に使う(D0049 PIT Bugfix、
  market_public_atへのFallback禁止が恒久原則)。今回のSnapshotの
  `retrieved_at`は実際には2026-08-16頃(ファイルmtime起源)であるため、
  歴史的な`as_of`(2024年)を指定すると`filter_usable_at()`が構造的に
  全件除外する。これは欠陥ではなく意図通りのFail Closed動作であり、
  DataGapとして記録する(値を推測で補うことは一切しない)。
- Positioning(price_derived、`lib.positioning.derived.price_derived.
  resolve_available_at()`): `session_close_at(observation_end)`基準
  (取引カレンダー由来、retrieved_atと無関係)。したがって2024年当時の
  Session Close時点で公開されていた価格由来のObservationは、2024年の
  `as_of`でも正しく利用可能と判定される。

## Scope

- 1社: 7203(トヨタ自動車、Local Snapshotにexplicit実データが存在する4社の
  うちの1つ、Investment Recommendationではなく単なる選定)。
- as_of: 2024-11-15 15:00 JST(2024-11-06のFY2025 2Q決算開示の後、
  Positioning Evidence Windowが2024年通年Bar内に収まる時点)。
- Fundamentals: 全20件のDisclosureのうち、主要Metric(sales/operating_
  profit/net_profit/eps/ordinary_profit)についてEvidence化を試みる
  (=> 上記の理由で全件filter_usable_atにより除外される見込み、実際に
  除外されることをこのScript自身が検証する)。
- Positioning: 直近10 Session分のTurnover Value + Volume Moving
  Average(20D、AdjFactor=1.0のためAdjusted=Raw)をEvidence化する
  (`lib.positioning.evidence.positioning_record_to_evidence()`
  ではなく、D0057を安全側に回避する`price_derived_record_to_
  evidence()`のみを使う)。
- Disclosures(EDINET等): 7203向けの実DisclosureDocumentは未取得のため
  含めない(DataGap、MISSING)。
- Consensus/Macro/News/Expectations: Phase5 v1 Scope外(既定で不使用、
  `DEFAULT_ALLOWED_CAPABILITIES`が構造的に強制)。

新しいJ-Quants Client・新しいEvidence Framework・新しいEngineはいずれも
作らない。既存の`LocalSnapshotAdapter`/`parse_financial_summary_payload`/
`equity_bars_payload_to_raw_bars`/`build_research_artifact`をそのまま
再利用する。
"""

from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parent.parent
LAB_ROOT = REPO_ROOT / "Japanese_Equity_Lab"
sys.path.insert(0, str(LAB_ROOT))

from lib.data_sources.convert import equity_bars_payload_to_raw_bars  # noqa: E402
from lib.data_sources.local_snapshot import LocalSnapshotAdapter  # noqa: E402
from lib.evidence.model import DataLayer, EvidenceRelation, filter_usable_at  # noqa: E402
from lib.evidence.research_artifact import (  # noqa: E402
    ConfidenceLevel,
    DataGap,
    DataGapStatus,
    NarrativeCase,
    ResearchConclusion,
    build_research_artifact,
    price_derived_record_to_evidence,
)
from lib.evidence.retrieval import ResearchQuestion  # noqa: E402
from lib.fundamentals.evidence import disclosure_metric_to_evidence  # noqa: E402
from lib.fundamentals.normalize import parse_financial_summary_payload  # noqa: E402
from lib.positioning.derived.price_derived import (  # noqa: E402
    build_turnover_value_records,
    build_volume_moving_average_records,
)
from lib.schemas.price_data import apply_split_adjustments  # noqa: E402
from lib.sources.catalog import SourceAuthorityClass  # noqa: E402

_JST = ZoneInfo("Asia/Tokyo")
_ENTITY = "7203"
_SNAPSHOT_DIR = LAB_ROOT / "01_data" / "raw" / "local_snapshot_input"
_KEY_METRIC_TYPES = frozenset({"sales", "operating_profit", "net_profit", "eps", "ordinary_profit"})
_POSITIONING_WINDOW_SESSIONS = 10
_VOLUME_MA_WINDOW = 20


def main() -> None:
    as_of = datetime(2024, 11, 15, 15, 0, tzinfo=_JST)
    adapter = LocalSnapshotAdapter(_SNAPSHOT_DIR)

    # --- Fundamentals: 実Snapshotから構築し、既存PIT Filterに委ねる ---
    fins_result = adapter.fetch_financial_statements(codes=[_ENTITY], start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))
    envelopes, metrics = parse_financial_summary_payload(fins_result.payload, retrieved_at=fins_result.retrieved_at)
    fundamentals_evidence = [
        disclosure_metric_to_evidence(env, m)
        for env in envelopes
        for m in metrics
        if m.envelope_id == env.envelope_id and m.metric_type in _KEY_METRIC_TYPES and m.value_availability.value == "PRESENT"
    ]

    # --- Positioning(price-derived): Session Close基準、retrieved_atと無関係 ---
    bars_result = adapter.fetch_equity_bars(codes=[_ENTITY], start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))
    raw_bars = equity_bars_payload_to_raw_bars(bars_result.payload)
    adjusted_bars = apply_split_adjustments(raw_bars, [])  # AdjFactor=1.0(通期)、実Corporate Action未検出

    sessions_on_or_before_as_of = sorted({b.session_date for b in raw_bars if b.session_date <= as_of.date()})
    window_sessions = set(sessions_on_or_before_as_of[-_POSITIONING_WINDOW_SESSIONS:])

    turnover_records = [
        r
        for r in build_turnover_value_records(raw_bars, retrieved_at=bars_result.retrieved_at)
        if r.observation_end in window_sessions
    ]
    volma_records = [
        r
        for r in build_volume_moving_average_records(
            adjusted_bars, window=_VOLUME_MA_WINDOW, retrieved_at=bars_result.retrieved_at
        )
        if r.observation_end in window_sessions
    ]
    positioning_evidence = [
        price_derived_record_to_evidence(
            rec,
            layer=DataLayer.DERIVED,
            source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
            originating_source="JQUANTS_SOURCE_DATA",
            delivery_provider="JQUANTS",
        )
        for rec in [*turnover_records, *volma_records]
        if rec.value_availability.value == "PRESENT"
    ]

    evidence_pool = [*fundamentals_evidence, *positioning_evidence]
    usable = filter_usable_at(evidence_pool, as_of)
    usable_fundamentals = [e for e in usable if e.capability.value == "FUNDAMENTAL"]
    usable_positioning = [e for e in usable if e.capability.value == "POSITIONING"]

    print(f"fundamentals_evidence_built={len(fundamentals_evidence)} usable={len(usable_fundamentals)}")
    print(f"positioning_evidence_built={len(positioning_evidence)} usable={len(usable_positioning)}")
    if usable_fundamentals:
        print("WARNING: fundamentals evidence unexpectedly usable at historical as_of (investigate before proceeding)")

    relations = {e.evidence_id: EvidenceRelation.NEUTRAL for e in usable_positioning}
    base_refs = tuple(e.evidence_id for e in usable_positioning)

    data_gaps = [
        DataGap(
            topic=f"Fundamentals Disclosure History ({_ENTITY}, key metrics)",
            status=DataGapStatus.UNAVAILABLE,
            note=(
                f"{len(fundamentals_evidence)}件のFundamentals Evidenceを実Snapshotから構築したが、"
                "available_at=envelope.retrieved_at(実際のLocal Fetch時刻、約2026-08-16)が"
                f"as_of({as_of.isoformat()})より後のため、filter_usable_at()により構造的に"
                "全件除外された(D0049 PIT Bugfix、market_public_atへのFallback禁止が恒久原則)。"
                "捏造・推測による補完はしていない。"
            ),
        ),
        DataGap(
            topic=f"Disclosure Documents / EDINET / TDnet ({_ENTITY})",
            status=DataGapStatus.MISSING,
            note="7203向けの実DisclosureDocumentは未取得(ローカルにEDINET Smoke Testデータはあるが別銘柄向け)。",
        ),
        DataGap(
            topic="Consensus / Analyst Estimates",
            status=DataGapStatus.MISSING,
            note="Phase5 v1 Scope外、Adapter未実装(DEFAULT_ALLOWED_CAPABILITIESにも含まれない)。",
        ),
    ]

    conclusion_rationale = (
        f"Fundamentals Evidence{len(fundamentals_evidence)}件を構築したが、全件がPIT Filterで除外された"
        f"(理由はDataGap参照)。Disclosure Documentsは未取得。利用可能なのはPositioning(price-derived、"
        f"直近{_POSITIONING_WINDOW_SESSIONS}Session分の売買代金・出来高移動平均)Evidence"
        f"{len(usable_positioning)}件のみであり、これ単独では企業の業績・妥当性についていかなる"
        "方向性の結論も支持しない(Observation != Investment Conclusion、高度なSignal化はしない、"
        "Phase4C原則)。したがってResearch ConclusionはINSUFFICIENT_EVIDENCEとする。"
    )

    artifact, packet = build_research_artifact(
        artifact_id="ART_STAGE3_1_7203_20241115_V1",
        entity_code=_ENTITY,
        question=ResearchQuestion(
            question_id="RQ_STAGE3_1_7203_0001",
            text=(
                "7203(トヨタ自動車)について、2024-11-15時点でこのLabが安全に"
                "参照できるReal Evidenceの範囲でどこまでResearchできるか"
            ),
            as_of=as_of,
            related_codes=(_ENTITY,),
        ),
        evidence_pool=evidence_pool,
        relations=relations,
        bull_case=NarrativeCase(summary="Bull Caseを支持するEvidenceは無い(Fundamentals全件がPIT Filterで除外)。"),
        base_case=NarrativeCase(
            summary=(
                f"直近{_POSITIONING_WINDOW_SESSIONS}Session分の売買代金・出来高移動平均(20D)は観測できるが、"
                "これらは記述統計であり業績・株価の妥当性についての解釈は含まない。"
            ),
            supporting_evidence_ids=base_refs,
        ),
        bear_case=NarrativeCase(summary="Bear Caseを支持するEvidenceも無い(同上)。"),
        data_confidence=ConfidenceLevel.LOW,
        evidence_confidence=ConfidenceLevel.MEDIUM,
        research_confidence=ConfidenceLevel.INSUFFICIENT,
        conclusion=ResearchConclusion.INSUFFICIENT_EVIDENCE,
        conclusion_rationale=conclusion_rationale,
        data_gaps=data_gaps,
    )

    print(f"artifact_id={artifact.artifact_id}")
    print(f"included_evidence_ids_count={len(artifact.included_evidence_ids)}")
    print(f"conclusion={artifact.conclusion.value}")
    print(
        f"data_confidence={artifact.data_confidence.value} "
        f"evidence_confidence={artifact.evidence_confidence.value} "
        f"research_confidence={artifact.research_confidence.value}"
    )
    for gap in artifact.data_gaps:
        print(f"data_gap: topic={gap.topic!r} status={gap.status.value}")

    out_dir = LAB_ROOT / "02_company_research" / "7203_Toyota_Motor"
    out_dir.mkdir(parents=True, exist_ok=True)
    from lib.registry.research_artifact_registry import ResearchArtifactRegistry

    registry = ResearchArtifactRegistry(out_dir / "research_artifacts.jsonl")
    registry.record(artifact)
    print(f"recorded_to={out_dir / 'research_artifacts.jsonl'}")


if __name__ == "__main__":
    main()
