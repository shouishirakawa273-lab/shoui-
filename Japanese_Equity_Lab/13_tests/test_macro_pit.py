"""`lib.macro.normalize`/`lib.macro.view`/`lib.macro.evidence`のPIT Test
(Phase4D)。Test IDはユーザーTask仕様のMACRO-*に対応する(期待値はPhase4D
要件から導出、実装からのコピーではない)。normalize.pyはSource非依存のため、
このRoundで実装した具体的Adapterが無くても、Test内で明示的な`resolve_
available_at`Callbackを注入して原則を検証できる。
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from lib.evidence.model import AvailabilityBasis, DataLayer, Frequency, ValueAvailability
from lib.macro.evidence import macro_record_to_evidence
from lib.macro.model import MacroRecord, SeasonalAdjustment
from lib.macro.normalize import build_revision_histories
from lib.macro.view import macro_as_of
from lib.sources.catalog import SourceAuthorityClass

RETRIEVED_AT = datetime(2026, 8, 19, 9, 0, tzinfo=UTC)
RELEASE_AT = datetime(2026, 8, 19, 8, 30, tzinfo=UTC)  # 7月分CPIの公表時刻(架空の確認済み値)


def _record(
    *,
    record_id: str,
    series_id: str = "JP_CPI_HEADLINE:ESTAT:MONTHLY",
    reference_period_start: date = date(2026, 7, 1),
    reference_period_end: date = date(2026, 7, 31),
    metric_name: str = "CPI_HEADLINE",
    value: str = "103.2",
    unit_override: str = "index",
    market_public_at: datetime | None = RELEASE_AT,
    market_public_at_basis: AvailabilityBasis = AvailabilityBasis.EXACT,
    seasonal_adjustment: SeasonalAdjustment = SeasonalAdjustment.NOT_SEASONALLY_ADJUSTED,
    retrieved_at: datetime = RETRIEVED_AT,
) -> MacroRecord:
    return MacroRecord(
        record_id=record_id,
        series_id=series_id,
        metric_name=metric_name,
        source_id="estat",
        frequency=Frequency.MONTHLY,
        reference_period_start=reference_period_start,
        reference_period_end=reference_period_end,
        raw_value=value,
        value=Decimal(value),
        unit=unit_override,
        seasonal_adjustment=seasonal_adjustment,
        value_availability=ValueAvailability.PRESENT,
        market_public_at=market_public_at,
        market_public_at_basis=market_public_at_basis if market_public_at is not None else AvailabilityBasis.UNKNOWN,
        retrieved_at=retrieved_at,
        normalizer_version="TEST_V1",
    )


def _release_resolver(record: MacroRecord) -> tuple[datetime, AvailabilityBasis]:
    """Test専用Resolver: market_public_at(確認済み公表時刻)が有ればそれを
    available_atとして使う(このRoundに実Adapterが無いため、原則検証用に
    Testが明示的に注入する)。"""
    if record.market_public_at is not None:
        return record.market_public_at, AvailabilityBasis.EXACT
    return record.retrieved_at, AvailabilityBasis.UNKNOWN


# --- MACRO-001: Reference Period Is Not Availability ---


def test_macro001_reference_period_alone_does_not_make_record_usable() -> None:
    record = _record(record_id="R1")
    histories = build_revision_histories([record], resolve_available_at=_release_resolver)
    mid_july = datetime(2026, 7, 20, tzinfo=UTC)  # reference_period内、公表前
    result = macro_as_of(histories, mid_july)
    assert result[record.series_id] is None


def test_macro001_usable_only_after_release() -> None:
    record = _record(record_id="R1")
    histories = build_revision_histories([record], resolve_available_at=_release_resolver)
    after_release = RELEASE_AT
    result = macro_as_of(histories, after_release)
    assert result[record.series_id] is not None


# --- MACRO-002: Release Lag ---


def test_macro002_between_reference_end_and_release_is_unavailable() -> None:
    """reference_period_end(7/31)を過ぎたが公表(8/19)前は利用不可。"""
    record = _record(record_id="R1")
    histories = build_revision_histories([record], resolve_available_at=_release_resolver)
    just_after_period_end = datetime(2026, 8, 1, tzinfo=UTC)
    result = macro_as_of(histories, just_after_period_end)
    assert result[record.series_id] is None


# --- MACRO-003: Unknown Provider Availability ---


def test_macro003_unknown_availability_basis_excluded_by_default() -> None:
    record = _record(record_id="R1")

    def _unknown_resolver(r: MacroRecord) -> tuple[datetime, AvailabilityBasis]:
        return r.retrieved_at, AvailabilityBasis.UNKNOWN

    histories = build_revision_histories([record], resolve_available_at=_unknown_resolver)
    far_future = datetime(2030, 1, 1, tzinfo=UTC)
    result = macro_as_of(histories, far_future)
    assert result[record.series_id] is None


def test_macro003_unknown_availability_included_only_when_explicit() -> None:
    record = _record(record_id="R1")

    def _unknown_resolver(r: MacroRecord) -> tuple[datetime, AvailabilityBasis]:
        return r.retrieved_at, AvailabilityBasis.UNKNOWN

    histories = build_revision_histories([record], resolve_available_at=_unknown_resolver)
    far_future = datetime(2030, 1, 1, tzinfo=UTC)
    result = macro_as_of(histories, far_future, include_unknown_availability=True)
    assert result[record.series_id] is not None


# --- MACRO-004: Revision PIT ---


def test_macro004_first_release_as_of_does_not_see_later_revision() -> None:
    first_release = _record(record_id="R_FIRST", value="103.0", market_public_at=RELEASE_AT)
    revised = _record(
        record_id="R_REVISED",
        value="103.5",
        market_public_at=datetime(2026, 9, 19, 8, 30, tzinfo=UTC),
        retrieved_at=datetime(2026, 9, 19, 9, 0, tzinfo=UTC),
    )
    histories = build_revision_histories([first_release, revised], resolve_available_at=_release_resolver)
    just_after_first_release = RELEASE_AT
    result = macro_as_of(histories, just_after_first_release)
    assert result[first_release.series_id] is not None
    assert result[first_release.series_id].value == "103.0"


# --- MACRO-005: Current Revision Leakage ---


def test_macro005_current_latest_value_not_leaked_into_historical_as_of() -> None:
    first_release = _record(record_id="R_FIRST", value="103.0", market_public_at=RELEASE_AT)
    revised = _record(
        record_id="R_REVISED",
        value="103.5",
        market_public_at=datetime(2026, 9, 19, 8, 30, tzinfo=UTC),
        retrieved_at=datetime(2026, 9, 19, 9, 0, tzinfo=UTC),
    )
    histories = build_revision_histories([first_release, revised], resolve_available_at=_release_resolver)
    # Currentの最新値は"103.5"(revised)だが、8月時点のas_ofには反映されない。
    historical_decision_at = datetime(2026, 8, 20, tzinfo=UTC)
    result = macro_as_of(histories, historical_decision_at)
    assert result[first_release.series_id].value == "103.0"
    assert result[first_release.series_id].value != "103.5"


# --- MACRO-006: No Zero Fill ---


def test_macro006_missing_raw_value_does_not_become_zero_in_source_version() -> None:
    record = _record(record_id="R1")
    record_missing = MacroRecord(
        record_id="R_MISSING",
        series_id=record.series_id,
        metric_name=record.metric_name,
        source_id=record.source_id,
        frequency=record.frequency,
        reference_period_start=record.reference_period_start,
        reference_period_end=record.reference_period_end,
        raw_value=None,
        value=None,
        unit=record.unit,
        seasonal_adjustment=record.seasonal_adjustment,
        value_availability=ValueAvailability.MISSING_OR_UNSPECIFIED,
        market_public_at=None,
        market_public_at_basis=AvailabilityBasis.UNKNOWN,
        retrieved_at=RETRIEVED_AT,
        normalizer_version="TEST_V1",
    )
    histories = build_revision_histories([record_missing], resolve_available_at=_release_resolver)
    version = histories[record.series_id].versions[0]
    assert version.value == ""  # Sentinelとしての空文字、"0"ではない
    assert version.value != "0"


# --- MACRO-007: Frequency Preservation ---


def test_macro007_monthly_and_quarterly_frequencies_are_not_conflated() -> None:
    monthly = _record(record_id="R_M", series_id="JP_CPI:ESTAT:MONTHLY")
    quarterly = MacroRecord(
        record_id="R_Q",
        series_id="JP_GDP:ESRI:QUARTERLY",
        metric_name="GDP_REAL",
        source_id="esri",
        frequency=Frequency.QUARTERLY,
        reference_period_start=date(2026, 4, 1),
        reference_period_end=date(2026, 6, 30),
        raw_value="550000",
        value=Decimal("550000"),
        unit="billion JPY",
        seasonal_adjustment=SeasonalAdjustment.SEASONALLY_ADJUSTED,
        value_availability=ValueAvailability.PRESENT,
        retrieved_at=RETRIEVED_AT,
        normalizer_version="TEST_V1",
    )
    assert monthly.frequency == Frequency.MONTHLY
    assert quarterly.frequency == Frequency.QUARTERLY
    assert monthly.frequency != quarterly.frequency


# --- MACRO-008: Unit Preservation ---


def test_macro008_yoy_percent_and_index_are_not_conflated() -> None:
    index_record = _record(record_id="R_IDX", unit_override="index")
    yoy_record = _record(record_id="R_YOY", unit_override="YoY percent")
    assert index_record.unit == "index"
    assert yoy_record.unit == "YoY percent"
    assert index_record.unit != yoy_record.unit


# --- MACRO-009: Seasonal Adjustment Separation ---


def test_macro009_sa_and_nsa_are_distinct_fields_not_auto_converted() -> None:
    sa_record = _record(record_id="R_SA", seasonal_adjustment=SeasonalAdjustment.SEASONALLY_ADJUSTED)
    nsa_record = _record(record_id="R_NSA", seasonal_adjustment=SeasonalAdjustment.NOT_SEASONALLY_ADJUSTED)
    assert sa_record.seasonal_adjustment != nsa_record.seasonal_adjustment


def test_macro009_no_seasonal_adjustment_conversion_function_exists() -> None:
    """SA<->NSAの自動変換関数がlib.macro配下に存在しないことを構造確認する
    (Phase4D要件§18「自動変換しない」)。"""
    import lib.macro.evidence as evidence_module
    import lib.macro.model as model_module
    import lib.macro.normalize as normalize_module
    import lib.macro.view as view_module

    for module in (model_module, normalize_module, view_module, evidence_module):
        source = module.__file__
        assert source is not None
        text = open(source, encoding="utf-8").read()
        assert "def convert" not in text.lower()
        assert "def to_seasonally_adjusted" not in text.lower()
        assert "def to_not_seasonally_adjusted" not in text.lower()


# --- MACRO-010: Date-only Publication(推測時刻の禁止) ---


def test_macro010_no_hardcoded_guessed_release_time_in_macro_modules() -> None:
    """Date-onlyの公表情報から特定Time(例: "08:30"、"15:00")を推測して
    埋めるCodeがlib.macro配下に存在しないことを構造確認する(Phase4D要件
    §11)。"""
    import lib.macro.evidence as evidence_module
    import lib.macro.model as model_module
    import lib.macro.normalize as normalize_module
    import lib.macro.view as view_module

    suspicious_patterns = ('"08:30"', "'08:30'", '"08, 30"', '"15:00"', "'15:00'", '"09:00"', "'09:00'")
    for module in (model_module, normalize_module, view_module, evidence_module):
        source = module.__file__
        assert source is not None
        text = open(source, encoding="utf-8").read()
        for pattern in suspicious_patterns:
            assert pattern not in text, f"{module.__name__}に推測時刻らしき値 {pattern} が含まれています"


# --- MACRO-011: Future Injection ---


def test_macro011_future_release_not_visible_to_past_as_of() -> None:
    future_record = _record(
        record_id="R_FUTURE",
        reference_period_start=date(2030, 1, 1),
        reference_period_end=date(2030, 1, 31),
        market_public_at=datetime(2030, 2, 19, 8, 30, tzinfo=UTC),
        value="999",
    )
    histories = build_revision_histories([future_record], resolve_available_at=_release_resolver)
    past_decision_at = datetime(2026, 8, 19, 9, 0, tzinfo=UTC)
    result = macro_as_of(histories, past_decision_at)
    assert result[future_record.series_id] is None


# --- MACRO-012: Raw Change Is Not Revision(構造確認) ---


def test_macro012_macro_modules_never_import_document_relationship() -> None:
    import lib.macro.evidence as evidence_module
    import lib.macro.model as model_module
    import lib.macro.normalize as normalize_module
    import lib.macro.view as view_module

    for module in (model_module, normalize_module, view_module, evidence_module):
        source = module.__file__
        assert source is not None
        text = open(source, encoding="utf-8").read()
        assert "DocumentRelationship" not in text
        assert "DuplicateRelationKind" not in text


# --- MACRO-013: Series Identity Safety ---


def test_macro013_similar_metric_names_with_different_series_id_are_not_merged() -> None:
    """CPI HeadlineとCPI Coreが似た名前でも、series_idが異なれば別Seriesの
    ままRevisionHistoryが分離されることを確認する(Display Nameだけでの
    Series統合をしない)。"""
    headline = _record(record_id="R_H", series_id="JP_CPI_HEADLINE:ESTAT:MONTHLY", metric_name="CPI_HEADLINE")
    core = _record(record_id="R_C", series_id="JP_CPI_CORE:ESTAT:MONTHLY", metric_name="CPI_CORE")
    histories = build_revision_histories([headline, core], resolve_available_at=_release_resolver)
    assert set(histories.keys()) == {headline.series_id, core.series_id}
    assert histories[headline.series_id].versions != histories[core.series_id].versions


# --- Defense in depth: pit-auditor Finding(Phase4D) ---


def test_tie_on_identical_available_at_is_input_order_dependent_known_limitation() -> None:
    """`RevisionHistory.as_of()`(`lib.evidence.model`、全Capability共通の
    既存Primitive)は、複数Versionが同一`available_at`に並んだ場合
    `max()`の仕様上「最初に出現した候補」を返す(Pythonの`max`は厳密に
    大きい場合のみ置き換えるため)。Date-only granularityのSourceで
    「1次速報」「2次速報」が偶然同一`available_at`に解決される場合、
    どちらが返るかは`build_revision_histories()`へ渡すRecordの順序に
    依存する——これは同じ入力なら同じ出力を返すという意味で
    Deterministic(MACRO-014)ではあるが、どちらのVintageが「正しい」かを
    Available Atだけからは判別できないという設計上の限界である
    (pit-auditor Finding、Phase4D。`lib.evidence.model.RevisionHistory`
    は4つのCapability[Fundamentals/Disclosures/Positioning/Macro]共通の
    Primitiveであり、Tie-break仕様の変更は本Round単独では行わない、
    Known Limitationとして記録するに留める、DECISIONS.md D0055参照)。
    このTestは現在の挙動を明示的に固定するのみで、正しさを主張しない。
    """
    first_in_list = _record(record_id="R_A", value="103.0", market_public_at=RELEASE_AT)
    second_in_list = _record(record_id="R_B", value="103.9", market_public_at=RELEASE_AT)  # 同一available_at

    histories_a_first = build_revision_histories([first_in_list, second_in_list], resolve_available_at=_release_resolver)
    histories_b_first = build_revision_histories([second_in_list, first_in_list], resolve_available_at=_release_resolver)

    result_a_first = macro_as_of(histories_a_first, RELEASE_AT)[first_in_list.series_id]
    result_b_first = macro_as_of(histories_b_first, RELEASE_AT)[first_in_list.series_id]

    assert result_a_first is not None
    assert result_b_first is not None
    assert result_a_first.value == "103.0"  # Listの先頭(first_in_list)が勝つ
    assert result_b_first.value == "103.9"  # Listの先頭(second_in_list)が勝つ
    assert result_a_first.value != result_b_first.value  # 入力順序で結果が変わることを明示的に固定する


# --- MACRO-014: Determinism ---


def test_macro014_same_input_produces_same_output() -> None:
    record = _record(record_id="R1")
    histories_a = build_revision_histories([record], resolve_available_at=_release_resolver)
    histories_b = build_revision_histories([record], resolve_available_at=_release_resolver)
    result_a = macro_as_of(histories_a, RELEASE_AT)
    result_b = macro_as_of(histories_b, RELEASE_AT)
    assert result_a[record.series_id].value == result_b[record.series_id].value
    assert result_a[record.series_id].available_at == result_b[record.series_id].available_at


# --- MACRO-015: No Investment Interpretation ---


def test_macro015_evidence_content_has_no_interpretive_language() -> None:
    record = _record(record_id="R1")
    evidence = macro_record_to_evidence(
        record,
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        originating_source="ESTAT",
        delivery_provider="ESTAT",
    )
    forbidden_terms = (
        "bullish",
        "bearish",
        "hawkish",
        "dovish",
        "buy",
        "sell",
        "利上げ",
        "利下げ",
        "景気後退",
        "好調",
        "悪化",
        "強気",
        "弱気",
        "inflation pressure",
        "rate hike",
    )
    for term in forbidden_terms:
        assert term not in evidence.content.lower(), f"Evidence Contentに解釈語 '{term}' が含まれています"


# --- Common Core Regression: 新規Evidence変換Primitiveを作らず既存を再利用 ---


def test_evidence_reuses_existing_evidence_record_and_source_metadata() -> None:
    record = _record(record_id="R1")
    evidence = macro_record_to_evidence(
        record,
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        originating_source="ESTAT",
        delivery_provider="ESTAT",
    )
    assert evidence.source.originating_source == "ESTAT"
    # market_public_atへはFallbackしない(retrieved_atが安全な下限として使われる)。
    assert evidence.source.available_at == record.retrieved_at
    assert evidence.layer == DataLayer.NORMALIZED


def test_naive_decision_at_rejected_by_macro_as_of() -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        macro_as_of({}, datetime(2026, 8, 18, 12, 0))


def test_resolver_returning_naive_datetime_rejected() -> None:
    record = _record(record_id="R1")

    def _naive_resolver(r: MacroRecord) -> tuple[datetime, AvailabilityBasis]:
        return datetime(2026, 8, 19, 8, 30), AvailabilityBasis.EXACT

    with pytest.raises(ValueError, match="tz-aware"):
        build_revision_histories([record], resolve_available_at=_naive_resolver)
