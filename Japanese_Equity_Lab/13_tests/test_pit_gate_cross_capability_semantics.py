"""Cross-Capability PIT Gate Consistency Review(D0057)。

Phase4E-1(D0056)でpit-auditorが報告したValidation Backlog #21
(「`global_market_as_of()`経路と`global_market_record_to_evidence()` +
`filter_usable_at()`経路のPIT判定が乖離しうる」)は、実際にはGlobal
Market固有の問題ではなく、`resolve_available_at`Callback Pattern(Session/
Period完了時刻を`AvailabilityBasis.INFERRED`で推定する)を持つ全Capability
(Positioning/Macro/Global Market)に共通するCommon Core既存挙動である。

このFileは**Timestampを一致させるTestではない**。2つの経路が構造的に
別々の「Available_atの推定戦略」を持つという既存Contractを固定する:

- **as_of経路**(`RevisionHistory.as_of()`経由、`lib.positioning.normalize.
  build_revision_histories`等): `resolve_available_at`Callbackが返す
  `available_at`を使う。Positioningの`price_derived.resolve_available_at`
  は「Session Close時刻」(Market Observation Completion Time、市場が
  その観測を実際に確定させた時刻)を`AvailabilityBasis.INFERRED`で
  推定する——`retrieved_at`(このLabが実際にいつ取得したか)を一切
  参照しない。
- **Evidence経路**(`EvidenceRecord.is_usable_at()`/`filter_usable_at()`
  経由): `positioning_record_to_evidence()`等は常に`record.retrieved_at`
  (Observed Safe Availability Timestamp、D0049/D0050)を`available_at`と
  する——`resolve_available_at`のSession Close推定を一切参照しない。

`lib.sources.catalog.SourceMetadata`のDocstringは`available_at`を
「provider_available_at相当」と定義しており、両経路とも**同じTarget概念
(System B: Reproducible System Simulation)を指そうとしている**。しかし
その推定戦略(Session Close推定 vs 実観測Retrieved_at)は独立しており、
どちらがどちらよりTargetに近いかを構造的に保証する仕組みは無い。

**分類: D. ARCHITECTURE_GAP**(D0057参照)。現在この2経路を実際に連結する
Execution Path(本物のAdapterのretrieved_atをEvidence変換経由で`filter_
usable_at()`へ渡す本番Pipeline)はRepository内に存在しない
(`positioning_record_to_evidence`/`filter_usable_at`はいずれも本番
`scripts/`・`app.py`から一切呼び出されていない、grep確認済み)ため
CURRENT_DEFECTではないが、将来Backtest System Bを実際に配線する際に
意味論衝突が起こりうる。
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from lib.evidence.model import AvailabilityBasis, DataLayer, Frequency, ValueAvailability, filter_usable_at
from lib.global_market.evidence import global_market_record_to_evidence as gm_to_evidence
from lib.global_market.model import GlobalMarketRecord, IndexReturnType, InstrumentCategory
from lib.global_market.normalize import build_revision_histories as gm_build_revision_histories
from lib.global_market.view import global_market_as_of
from lib.market_calendar import session_close_at
from lib.positioning.derived.price_derived import build_turnover_value_records, resolve_available_at
from lib.positioning.evidence import positioning_record_to_evidence
from lib.positioning.normalize import build_revision_histories as positioning_build_revision_histories
from lib.positioning.view import positioning_as_of
from lib.schemas.price_data import RawOHLCVBar
from lib.sources.catalog import SourceAuthorityClass

# --- A/B. 両経路の推定戦略が互いに独立であることの構造確認(Positioning、実Adapter) ---


def test_as_of_path_available_at_is_independent_of_retrieved_at() -> None:
    """`resolve_available_at`(as_of経路)はSession Closeのみに依存し、
    `retrieved_at`をどう変えても`available_at`(=SourceVersion.available_at)は
    変化しない(構造確認: as_of経路がSystem Bの「Session Close推定」戦略の
    みを使い、`retrieved_at`Observed Factを一切混ぜないことの直接証拠)。"""
    session_date = date(2026, 8, 18)
    bar = RawOHLCVBar(code="7203", session_date=session_date, open=100.0, high=100.0, low=100.0, close=100.0, volume=1000.0)

    early_retrieved_at = datetime(2026, 8, 18, 5, 0, tzinfo=UTC)  # Session開始前
    late_retrieved_at = datetime(2026, 8, 20, 0, 0, tzinfo=UTC)  # Session Closeの2日後

    records_early = build_turnover_value_records([bar], retrieved_at=early_retrieved_at)
    records_late = build_turnover_value_records([bar], retrieved_at=late_retrieved_at)

    histories_early = positioning_build_revision_histories(records_early, resolve_available_at=resolve_available_at)
    histories_late = positioning_build_revision_histories(records_late, resolve_available_at=resolve_available_at)

    series_id = records_early[0].series_id
    version_early = histories_early[series_id].versions[0]
    version_late = histories_late[series_id].versions[0]

    # available_at(as_of経路)はretrieved_atの値に関わらず常にSession Closeと一致する。
    assert version_early.available_at == session_close_at(session_date)
    assert version_late.available_at == session_close_at(session_date)
    assert version_early.available_at == version_late.available_at


def test_evidence_path_available_at_is_independent_of_session_close() -> None:
    """`positioning_record_to_evidence()`(Evidence経路)は`record.retrieved_at`
    のみに依存し、Session Close(`resolve_available_at`が計算する値)を
    一切参照しない(構造確認、Evidence経路が「実観測Retrieved_at」戦略のみを
    使うことの直接証拠)。"""
    session_date = date(2026, 8, 18)
    bar = RawOHLCVBar(code="7203", session_date=session_date, open=100.0, high=100.0, low=100.0, close=100.0, volume=1000.0)
    retrieved_at = datetime(2026, 8, 18, 5, 0, tzinfo=UTC)  # Session Close(15:00 JST)より前

    record = build_turnover_value_records([bar], retrieved_at=retrieved_at)[0]
    evidence = positioning_record_to_evidence(
        record,
        layer=DataLayer.DERIVED,
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        originating_source="JQUANTS",
        delivery_provider="JQUANTS",
    )
    # Evidence経路のavailable_atはretrieved_atそのもの——Session Close(15:00 JST)より
    # 前であっても、Session Closeの値へは一切引き上げられない。
    assert evidence.source.available_at == retrieved_at
    assert evidence.source.available_at != session_close_at(session_date)


# --- C/E. Failure Example: retrieved_atがSession Closeより前の場合の実際の乖離(Positioning、実Adapter) ---


def test_evidence_path_leaks_earlier_than_as_of_path_when_retrieved_before_session_close() -> None:
    """Failure Example(D0057 §7相当、日本市場版): あるBarをSession Close
    (15:00 JST)より前にRetrieveした場合(例: 実際には前営業日分の確定Bar
    だが、Batch取得の都合でretrieved_atが早い、または将来Providerが
    Intraday/Current値をSession中に返す場合)、Evidence経路はas_of経路より
    早い時刻からそのRecordを「利用可能」と判定してしまう。

    これはCURRENT_DEFECTではない(以下いずれの経路も本番Pipelineに実際には
    配線されていない、D0057 Repository Reality Check参照)が、両経路を
    将来接続した場合に起こりうる意味論衝突を再現するSemantic Contract
    Testである。
    """
    session_date = date(2026, 8, 18)
    close_at = session_close_at(session_date)  # 2026-08-18 15:00 JST
    retrieved_at = close_at - timedelta(hours=6)  # Session Closeの6時間前に取得(想定シナリオ)
    decision_at = close_at - timedelta(hours=3)  # retrieved_atとclose_atの間

    bar = RawOHLCVBar(code="7203", session_date=session_date, open=100.0, high=100.0, low=100.0, close=100.0, volume=1000.0)
    record = build_turnover_value_records([bar], retrieved_at=retrieved_at)[0]

    # as_of経路: Session Closeより前なので正しく利用不可。
    histories = positioning_build_revision_histories([record], resolve_available_at=resolve_available_at)
    as_of_result = positioning_as_of(histories, decision_at)
    assert as_of_result[record.series_id] is None

    # Evidence経路: retrieved_at(Session Closeの6時間前)のみを基準にするため、
    # 同じdecision_atで誤って「利用可能」と判定する(2経路の乖離の直接再現)。
    evidence = positioning_record_to_evidence(
        record,
        layer=DataLayer.DERIVED,
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        originating_source="JQUANTS",
        delivery_provider="JQUANTS",
    )
    usable_via_evidence = filter_usable_at([evidence], decision_at)
    assert len(usable_via_evidence) == 1


def test_evidence_path_agrees_with_as_of_path_when_retrieved_after_session_close() -> None:
    """Well-behaved Ordering: retrieved_atがSession Closeより後(=このLabの
    現行運用が実際に想定する順序、Bar確定後に取得)であれば、Evidence経路は
    as_of経路より**保守的**(遅い、またはSameな判定)になり、乖離しない
    (Failure Exampleとの対比、`retrieved_at >= available_at`の場合は安全
    であることの直接確認)。"""
    session_date = date(2026, 8, 18)
    close_at = session_close_at(session_date)
    retrieved_at = close_at + timedelta(minutes=10)  # Session Close後に取得(通常の運用)
    decision_at_before_close = close_at - timedelta(minutes=1)
    decision_at_between = close_at + timedelta(minutes=5)  # Closeの後、Retrieved_atの前
    decision_at_after_retrieved = close_at + timedelta(minutes=15)

    bar = RawOHLCVBar(code="7203", session_date=session_date, open=100.0, high=100.0, low=100.0, close=100.0, volume=1000.0)
    record = build_turnover_value_records([bar], retrieved_at=retrieved_at)[0]
    evidence = positioning_record_to_evidence(
        record,
        layer=DataLayer.DERIVED,
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        originating_source="JQUANTS",
        delivery_provider="JQUANTS",
    )
    histories = positioning_build_revision_histories([record], resolve_available_at=resolve_available_at)

    # Close前: 両経路とも利用不可。
    assert positioning_as_of(histories, decision_at_before_close)[record.series_id] is None
    assert len(filter_usable_at([evidence], decision_at_before_close)) == 0

    # CloseとRetrieved_atの間: as_of経路は利用可能(Session Closeは過ぎている)だが、
    # Evidence経路はまだ利用不可(Retrieved_atに達していない) — Evidence経路がより
    # 保守的(安全側)であり、Future Leakageの方向ではない。
    assert positioning_as_of(histories, decision_at_between)[record.series_id] is not None
    assert len(filter_usable_at([evidence], decision_at_between)) == 0

    # Retrieved_at後: 両経路とも利用可能で一致する。
    assert positioning_as_of(histories, decision_at_after_retrieved)[record.series_id] is not None
    assert len(filter_usable_at([evidence], decision_at_after_retrieved)) == 1


# --- D. 構造確認: SourceMetadata/EvidenceRecordにはAvailabilityBasis相当の概念が無い ---


def test_evidence_record_source_metadata_has_no_availability_basis_field() -> None:
    """`lib.evidence.model.RevisionHistory.as_of()`は`AvailabilityBasis`
    (EXACT/OBSERVED/INFERRED/UNKNOWN)でUNKNOWNを既定除外するが、
    `EvidenceRecord`/`SourceMetadata`にはこれに相当するField自体が存在
    しない(構造確認、D0057 Capability Matrixの「Evidence AvailabilityBasis
    列」がどのCapabilityでも常に'N/A(Fieldなし)'である根拠)。"""
    import dataclasses

    from lib.sources.catalog import SourceMetadata

    field_names = {f.name for f in dataclasses.fields(SourceMetadata)}
    assert "availability_basis" not in field_names


# --- Global Market版(D0056で既に固定済みの同型Testが存在することの確認、二重管理しない) ---


def test_global_market_records_the_same_divergence_pattern_independently() -> None:
    """Global Marketも同型の構造(Session/Period完了時刻推定 vs retrieved_at)を
    持つことを、独立した最小Sanity Checkとして確認する(Global Market固有の
    詳細Testは`test_global_market_pit.py::test_global_market_as_of_and_
    evidence_filter_usable_at_can_disagree_known_limitation`が既に持つため
    ここでは重複させず、Positioning/Global Marketで同型のPatternが再現する
    こと自体の確認に留める)。"""
    from zoneinfo import ZoneInfo

    session_date = date(2026, 8, 18)
    close_at = datetime(2026, 8, 18, 16, 0, tzinfo=ZoneInfo("America/New_York"))
    early_retrieved_at = close_at - timedelta(hours=2)
    decision_at = close_at - timedelta(hours=1)

    def _resolver(r: GlobalMarketRecord) -> tuple[datetime, AvailabilityBasis]:
        return close_at, AvailabilityBasis.INFERRED

    record = GlobalMarketRecord(
        record_id="R1",
        series_id="SPX_PRICE_INDEX:PROVIDER:DAILY:2026-08-18",
        instrument_category=InstrumentCategory.EQUITY_INDEX,
        index_return_type=IndexReturnType.PRICE_RETURN,
        metric_name="SPX_PRICE_INDEX",
        source_id="PROVIDER",
        frequency=Frequency.DAILY,
        session_date=session_date,
        market_timezone="America/New_York",
        raw_value="5000.12",
        value=Decimal("5000.12"),
        unit="index points",
        value_availability=ValueAvailability.PRESENT,
        retrieved_at=early_retrieved_at,
        normalizer_version="TEST_V1",
    )
    histories = gm_build_revision_histories([record], resolve_available_at=_resolver)
    assert global_market_as_of(histories, decision_at)[record.series_id] is None

    evidence = gm_to_evidence(
        record,
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        originating_source="PROVIDER",
        delivery_provider="PROVIDER",
    )
    assert len(filter_usable_at([evidence], decision_at)) == 1
