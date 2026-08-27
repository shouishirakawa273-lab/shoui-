"""Phase4A(D0043): Financial Summary Normalizerのテスト。

`13_tests/fixtures/financial_summary_v2.json`(J-Quants V2 `/v2/fins/summary`の
生レスポンス形状を模したGolden Fixture、合成データ)を使う。Field名は全て未検証
(DECISIONS.md D0043参照)。
"""

from __future__ import annotations

import copy
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from lib.evidence.model import ValueAvailability
from lib.fundamentals.model import ActualOrForecast, ConsolidationScope, FiscalYearTarget, PeriodBasis, PeriodType
from lib.fundamentals.normalize import build_revision_histories, parse_financial_summary_payload, resolve_value_availability
from lib.sources.entity_registry import EntityIdentifierMapping, EntityRegistry, MappingConfidence

_FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "financial_summary_v2.json"
_RETRIEVED_AT = datetime(2026, 1, 1, tzinfo=UTC)


def _load_payload() -> list[dict[str, object]]:
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))["data"]


# --- Test 1: Raw payload immutable ---


def test_parsing_does_not_mutate_raw_payload() -> None:
    payload = _load_payload()
    payload_copy = copy.deepcopy(payload)
    parse_financial_summary_payload(payload, retrieved_at=_RETRIEVED_AT)
    assert payload == payload_copy


# --- Test 2: Provider 5桁CodeとInternal Codeが混同されない ---


def test_provider_code_and_internal_code_are_kept_distinct() -> None:
    envelopes, _ = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    toyota = next(e for e in envelopes if e.internal_code == "7203")
    assert toyota.provider_code == "72030"
    assert toyota.provider_code != toyota.internal_code


# --- Test 3: ActualとForecastを混同しない ---


def test_actual_and_forecast_are_never_the_same_series() -> None:
    _, metrics = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    toyota_op = [m for m in metrics if m.envelope_id.startswith("ENV_7203") and "operating_profit" in m.metric_type]
    actuals = {m.series_id for m in toyota_op if m.actual_or_forecast == ActualOrForecast.ACTUAL}
    forecasts = {m.series_id for m in toyota_op if m.actual_or_forecast == ActualOrForecast.COMPANY_FORECAST}
    assert actuals.isdisjoint(forecasts)


# --- Test 4: Current FYとNext FYを混同しない ---


def test_current_and_next_fiscal_year_forecasts_are_never_the_same_series() -> None:
    _, metrics = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    forecast_metrics = [m for m in metrics if m.actual_or_forecast == ActualOrForecast.COMPANY_FORECAST]
    current = {m.series_id for m in forecast_metrics if m.fiscal_year_target == FiscalYearTarget.CURRENT_FISCAL_YEAR}
    next_year = {m.series_id for m in forecast_metrics if m.fiscal_year_target == FiscalYearTarget.NEXT_FISCAL_YEAR}
    assert current.isdisjoint(next_year)


# --- Test 5: ConsolidatedとNon-Consolidatedを混同しない ---


def test_consolidated_and_non_consolidated_are_never_the_same_series() -> None:
    _, metrics = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    consolidated = {m.series_id for m in metrics if m.consolidation_scope == ConsolidationScope.CONSOLIDATED}
    non_consolidated = {m.series_id for m in metrics if m.consolidation_scope == ConsolidationScope.NON_CONSOLIDATED}
    assert consolidated.isdisjoint(non_consolidated)
    # Consolidation ScopeはDocTypeからの推測ではなく、Field群(Sales/OP vs NCSales/NCOP)で決まる。
    sales_metric = next(m for m in metrics if m.source_field == "Sales")
    ncsales_metric = next((m for m in metrics if m.source_field == "NCSales"), None)
    assert sales_metric.consolidation_scope == ConsolidationScope.CONSOLIDATED
    if ncsales_metric is not None:
        assert ncsales_metric.consolidation_scope == ConsolidationScope.NON_CONSOLIDATED


# --- Test 6: 2Q cumulativeをQ2 standalone扱いしない ---


# Stage 3.7(D0081)でPeriodBasis.POINT_IN_TIME(TA/ShEq/EqAR)を追加したため、
# 「period_basisは常にCUMULATIVE」という旧Invariantはもはや成立しない。
# 「Flow系はCUMULATIVEのまま、Stock系はPOINT_IN_TIME、STANDALONEは
# どちらの経路からも自動生成されない」という新Invariantへ置換する。
_FLOW_METRIC_TYPES = frozenset(
    {
        "sales",
        "operating_profit",
        "net_profit",
        "ordinary_profit",
        "eps",
        "cash_flow_from_operations",
        "cash_flow_from_investing",
        "cash_flow_from_financing",
    }
)
_STOCK_METRIC_TYPES = frozenset({"total_assets", "provider_reported_sheq", "provider_reported_eqar"})


def test_flow_metrics_remain_cumulative() -> None:
    """Phase4AはProviderの値をそのまま保持するのみで、2Q累計からQ2単独値を
    計算する導出は行わない(Flow系Metricのperiod_basisは引き続きCUMULATIVE)。"""
    _, metrics = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    flow_metrics = [m for m in metrics if m.metric_type in _FLOW_METRIC_TYPES]
    assert flow_metrics
    assert all(m.period_basis == PeriodBasis.CUMULATIVE for m in flow_metrics)


def test_stock_metrics_are_point_in_time() -> None:
    """Stage 3.7(D0081): Stock系Metric(TA/ShEq/EqAR)のperiod_basisは
    POINT_IN_TIME(期間累計Flowではなく特定value_date時点のSnapshot)。"""
    _, metrics = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    stock_metrics = [m for m in metrics if m.metric_type in _STOCK_METRIC_TYPES]
    assert stock_metrics
    assert all(m.period_basis == PeriodBasis.POINT_IN_TIME for m in stock_metrics)


def test_standalone_is_never_automatically_generated() -> None:
    """CUMULATIVE(既存Flow)・POINT_IN_TIME(Stage 3.7 Stock)いずれの経路からも
    STANDALONEを自動導出しない(Phase4Aの既存方針を維持)。"""
    _, metrics = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    assert not any(m.period_basis == PeriodBasis.STANDALONE for m in metrics)


def test_every_metric_field_map_descriptor_specifies_period_basis() -> None:
    """`_METRIC_FIELD_MAP`の全DescriptorがPeriodBasisを明示的に持つ(暗黙default
    禁止、Stage 3.7要件)。5要素Tuple(source_field, actual_or_forecast,
    fiscal_year_target, consolidation_scope, period_basis)であることを構造的に
    確認する。"""
    from lib.fundamentals.normalize import _METRIC_FIELD_MAP

    assert _METRIC_FIELD_MAP
    for metric_type, descriptor in _METRIC_FIELD_MAP.items():
        assert len(descriptor) == 5, f"metric_type={metric_type!r}: PeriodBasisが明示されていません({descriptor!r})"
        assert isinstance(descriptor[4], PeriodBasis), f"metric_type={metric_type!r}: 5番目の要素がPeriodBasisではありません"


# --- Test 7: 0とNULLを区別 ---


def test_zero_value_is_present_and_distinct_from_blank() -> None:
    assert resolve_value_availability("0", accounting_standard=None, metric_type="operating_profit") == ValueAvailability.PRESENT
    assert resolve_value_availability("", accounting_standard=None, metric_type="operating_profit") != ValueAvailability.PRESENT
    assert resolve_value_availability(None, accounting_standard=None, metric_type="operating_profit") != ValueAvailability.PRESENT


def test_present_zero_value_parses_to_decimal_zero_not_none() -> None:
    envelopes, metrics = parse_financial_summary_payload(
        [{"Code": "9999", "DiscDate": "2024-01-01", "DiscTime": "15:00", "CurPerType": "FY", "OP": "0"}],
        retrieved_at=_RETRIEVED_AT,
    )
    op = next(m for m in metrics if m.metric_type == "operating_profit")
    assert op.value_availability == ValueAvailability.PRESENT
    assert op.value == Decimal("0")


# --- Test 8/9: NOT_APPLICABLEと0を区別、IFRS ordinary profit blankを0扱いしない ---


def test_ifrs_blank_ordinary_profit_is_not_applicable_not_zero() -> None:
    _, metrics = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    sony_ordinary_profit = next(m for m in metrics if m.envelope_id.startswith("ENV_6758") and m.metric_type == "ordinary_profit")
    assert sony_ordinary_profit.value_availability == ValueAvailability.NOT_APPLICABLE
    assert sony_ordinary_profit.value is None
    assert sony_ordinary_profit.value != 0


def test_blank_without_confirmed_reason_is_missing_or_unspecified_not_not_applicable() -> None:
    """会計基準から確認できない空値は、NOT_DISCLOSEDと決めつけずMISSING_OR_UNSPECIFIEDとする。"""
    _, metrics = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    toyota_next_year = [
        m for m in metrics if m.envelope_id == "ENV_7203_20240510001" and m.fiscal_year_target.value == "NEXT_FISCAL_YEAR"
    ]
    assert toyota_next_year
    assert all(m.value_availability == ValueAvailability.MISSING_OR_UNSPECIFIED for m in toyota_next_year)


# --- Test 10: DiscDate/DiscTimeから作るmarket_public_atがtz-aware ---


def test_market_public_at_is_tz_aware_asia_tokyo_when_both_fields_present() -> None:
    envelopes, _ = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    toyota_first = next(e for e in envelopes if e.envelope_id == "ENV_7203_20240510001")
    assert toyota_first.market_public_at is not None
    assert toyota_first.market_public_at.tzinfo is not None
    assert toyota_first.market_public_at == datetime(2024, 5, 10, 15, 0, tzinfo=ZoneInfo("Asia/Tokyo"))


def test_market_public_at_is_none_when_disc_time_missing_not_defaulted_to_1500() -> None:
    """DiscTimeが無い場合、15:00等を推測で補完しない(D0043)。"""
    envelopes, _ = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    biprogy = next(e for e in envelopes if e.envelope_id == "ENV_8056_20240520001")
    assert biprogy.disclosure_time == ""
    assert biprogy.market_public_at is None


# --- 未知のCurPerType/DocTypeはfail closed(即例外で全処理停止しない) ---


def test_unknown_cur_per_type_fails_closed_to_other_not_exception(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("WARNING"):
        envelopes, _ = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    biprogy = next(e for e in envelopes if e.envelope_id == "ENV_8056_20240520001")
    assert biprogy.current_period_type == PeriodType.OTHER
    assert "6Q" in caplog.text


def test_unknown_doc_type_fails_closed_accounting_standard_to_none(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("WARNING"):
        envelopes, _ = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    toyota_first = next(e for e in envelopes if e.envelope_id == "ENV_7203_20240510001")
    assert toyota_first.accounting_standard is None
    assert "SYNTH_DOC_TYPE" in caplog.text


# --- Provider Schema Evolution: 未知の追加Fieldでも壊れない ---


def test_unknown_extra_raw_field_does_not_break_normalizer() -> None:
    envelopes, metrics = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    tis = next(e for e in envelopes if e.envelope_id == "ENV_3626_20240525001")
    assert tis.internal_code == "3626"
    tis_metrics = [m for m in metrics if m.envelope_id == tis.envelope_id]
    assert len(tis_metrics) > 0


def test_unknown_extra_raw_field_preserved_in_raw_payload() -> None:
    payload = _load_payload()
    row = next(r for r in payload if r["Code"] == "36260")
    assert row["FutureProviderFieldNotYetKnown"] == "unrecognized-but-preserved"


# --- Entity Registry integration ---


def test_entity_registry_resolves_canonical_entity_id_when_mapped() -> None:
    registry = EntityRegistry(
        [
            EntityIdentifierMapping(
                issuer_id="ISSUER_TOYOTA",
                provider_identifiers={"jquants": "72030"},
                canonical_name="トヨタ自動車",
                mapping_confidence=MappingConfidence.HIGH,
            )
        ]
    )
    envelopes, _ = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT, entity_registry=registry)
    toyota_first = next(e for e in envelopes if e.envelope_id == "ENV_7203_20240510001")
    assert toyota_first.canonical_entity_id == "ISSUER_TOYOTA"


def test_entity_registry_leaves_canonical_entity_id_none_when_unmapped() -> None:
    """マッピングが不明な場合は推測しない。"""
    registry = EntityRegistry([])
    envelopes, _ = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT, entity_registry=registry)
    toyota_first = next(e for e in envelopes if e.envelope_id == "ENV_7203_20240510001")
    assert toyota_first.canonical_entity_id is None


# --- Test 15/property: Revision前後でas_of Viewが変化する ---


def test_forecast_revision_builds_multiple_versions_in_same_series() -> None:
    envelopes, metrics = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    histories = build_revision_histories(envelopes, metrics)
    op_forecast_series = [
        sid for sid in histories if sid.startswith("7203|operating_profit_current_year_forecast|CURRENT_FISCAL_YEAR|FY|")
    ]
    assert len(op_forecast_series) == 1
    history = histories[op_forecast_series[0]]
    assert len(history.versions) == 2
    values = sorted(v.value for v in history.versions)
    assert values == ["105000", "120000"]


# --- Stage 3.6(D0079): Cash Flow(CFO/CFI/CFF)v1 ---


def test_cfo_field_maps_correctly() -> None:
    _, metrics = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    m = next(x for x in metrics if x.envelope_id == "ENV_7203_20240510001" and x.metric_type == "cash_flow_from_operations")
    assert m.source_field == "CFO"
    assert m.value == Decimal("500000")
    assert m.value_availability == ValueAvailability.PRESENT


def test_cfi_field_maps_correctly() -> None:
    _, metrics = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    m = next(x for x in metrics if x.envelope_id == "ENV_7203_20240510001" and x.metric_type == "cash_flow_from_investing")
    assert m.source_field == "CFI"
    assert m.value == Decimal("-300000")
    assert m.value_availability == ValueAvailability.PRESENT


def test_cff_field_maps_correctly() -> None:
    _, metrics = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    m = next(x for x in metrics if x.envelope_id == "ENV_7203_20240510001" and x.metric_type == "cash_flow_from_financing")
    assert m.source_field == "CFF"
    assert m.value == Decimal("0")
    assert m.value_availability == ValueAvailability.PRESENT


def test_cash_flow_metrics_are_actual_not_forecast() -> None:
    _, metrics = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    cash_flow_metrics = [
        m
        for m in metrics
        if m.metric_type in {"cash_flow_from_operations", "cash_flow_from_investing", "cash_flow_from_financing"}
    ]
    assert cash_flow_metrics
    assert all(m.actual_or_forecast == ActualOrForecast.ACTUAL for m in cash_flow_metrics)


def test_cash_flow_metrics_are_consolidated() -> None:
    _, metrics = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    cash_flow_metrics = [
        m
        for m in metrics
        if m.metric_type in {"cash_flow_from_operations", "cash_flow_from_investing", "cash_flow_from_financing"}
    ]
    assert cash_flow_metrics
    assert all(m.consolidation_scope == ConsolidationScope.CONSOLIDATED for m in cash_flow_metrics)


def test_cash_flow_metrics_are_always_cumulative() -> None:
    """累計Flowを2Q単独等へ勝手にderivationしない(period_basisは常にCUMULATIVE)。"""
    _, metrics = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    cash_flow_metrics = [
        m
        for m in metrics
        if m.metric_type in {"cash_flow_from_operations", "cash_flow_from_investing", "cash_flow_from_financing"}
    ]
    assert cash_flow_metrics
    assert all(m.period_basis == PeriodBasis.CUMULATIVE for m in cash_flow_metrics)


def test_cash_flow_1q_period_start_end_from_fy_start() -> None:
    envelopes, _ = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    env = next(e for e in envelopes if e.envelope_id == "ENV_7203_20240801001")
    assert env.current_period_type == PeriodType.Q1
    assert env.current_period_start == date(2024, 4, 1)
    assert env.current_period_end == date(2024, 6, 30)


def test_cash_flow_2q_period_start_end_from_fy_start() -> None:
    envelopes, _ = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    env = next(e for e in envelopes if e.envelope_id == "ENV_7203_20241101001")
    assert env.current_period_type == PeriodType.Q2
    assert env.current_period_start == date(2024, 4, 1)
    assert env.current_period_end == date(2024, 9, 30)


def test_cash_flow_fy_period_start_end() -> None:
    envelopes, _ = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    env = next(e for e in envelopes if e.envelope_id == "ENV_7203_20240510001")
    assert env.current_period_type == PeriodType.FY
    assert env.current_period_start == date(2023, 4, 1)
    assert env.current_period_end == date(2024, 3, 31)


def test_cash_flow_2q_is_not_treated_as_standalone_q2() -> None:
    """2Qのperiod_startはFY開始日(2024-04-01)であり、Q2単独の開始日
    (2024-07-01相当)ではない -- 2Q累計値をQ2 standalone値と解釈していないことの確認。"""
    envelopes, _ = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    env = next(e for e in envelopes if e.envelope_id == "ENV_7203_20241101001")
    assert env.current_period_start == env.current_fiscal_year_start
    assert env.current_period_start != date(2024, 7, 1)


def test_negative_cash_flow_from_investing_remains_valid_decimal() -> None:
    """負のCFIをInvalid扱いしない(単なる符号付きDecimal)。"""
    _, metrics = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    m = next(x for x in metrics if x.envelope_id == "ENV_7203_20240510001" and x.metric_type == "cash_flow_from_investing")
    assert m.value_availability == ValueAvailability.PRESENT
    assert m.value == Decimal("-300000")
    assert m.value < 0


def test_zero_cash_flow_from_financing_remains_present_not_missing() -> None:
    _, metrics = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    m = next(x for x in metrics if x.envelope_id == "ENV_7203_20240510001" and x.metric_type == "cash_flow_from_financing")
    assert m.value_availability == ValueAvailability.PRESENT
    assert m.value == Decimal("0")
    assert m.value is not None


def test_missing_cash_flow_field_is_missing_or_unspecified() -> None:
    """CFO/CFI/CFF自体がRaw Payloadに存在しないDisclosure(ENV_7203_20240809001)では、
    NOT_APPLICABLEではなくMISSING_OR_UNSPECIFIEDとして扱う(会計基準から不存在と
    確認できたわけではないため)。"""
    _, metrics = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    m = next(x for x in metrics if x.envelope_id == "ENV_7203_20240809001" and x.metric_type == "cash_flow_from_operations")
    assert m.value_availability == ValueAvailability.MISSING_OR_UNSPECIFIED
    assert m.value is None


# --- Stage 3.7(D0081): Balance Sheet Point-in-Time(TA/ShEq/EqAR)v1 ---


def test_ta_maps_correctly_and_is_point_in_time() -> None:
    _, metrics = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    m = next(x for x in metrics if x.envelope_id == "ENV_7203_20240510001" and x.metric_type == "total_assets")
    assert m.source_field == "TA"
    assert m.value == Decimal("90114296000000")
    assert m.value_availability == ValueAvailability.PRESENT
    assert m.period_basis == PeriodBasis.POINT_IN_TIME


def test_sheq_maps_correctly_and_is_point_in_time() -> None:
    _, metrics = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    m = next(x for x in metrics if x.envelope_id == "ENV_7203_20240510001" and x.metric_type == "provider_reported_sheq")
    assert m.source_field == "ShEq"
    assert m.value == Decimal("34220991000000")
    assert m.value_availability == ValueAvailability.PRESENT
    assert m.period_basis == PeriodBasis.POINT_IN_TIME


def test_eqar_maps_correctly_and_is_point_in_time() -> None:
    _, metrics = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    m = next(x for x in metrics if x.envelope_id == "ENV_7203_20240510001" and x.metric_type == "provider_reported_eqar")
    assert m.source_field == "EqAR"
    assert m.value == Decimal("0.38")
    assert m.value_availability == ValueAvailability.PRESENT
    assert m.period_basis == PeriodBasis.POINT_IN_TIME


def test_stock_metric_period_type_reflects_disclosure_cadence_not_accumulation() -> None:
    """Stock MetricのPeriodType(1Q/2Q/3Q/FY)は「どのDisclosure cadenceで報告された
    Snapshotか」を表すのみで、その期間を累積した値という意味ではない(§5)。"""
    envelopes, metrics = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    ta_2q = next(m for m in metrics if m.envelope_id == "ENV_7203_20241101001" and m.metric_type == "total_assets")
    envelope_2q = next(e for e in envelopes if e.envelope_id == "ENV_7203_20241101001")
    assert ta_2q.period_type == PeriodType.Q2
    assert ta_2q.value == Decimal("89169296000000")
    assert envelope_2q.current_period_end == date(2024, 9, 30)


def test_negative_sheq_and_eqar_remain_valid_decimal() -> None:
    """負のShEq/EqARをInvalid扱いしない(単なる符号付きDecimal、§16 Interpretation
    Boundaryとは無関係にParse層はFactをそのまま保持する)。"""
    _, metrics = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    sheq = next(m for m in metrics if m.envelope_id == "ENV_3626_20240525001" and m.metric_type == "provider_reported_sheq")
    eqar = next(m for m in metrics if m.envelope_id == "ENV_3626_20240525001" and m.metric_type == "provider_reported_eqar")
    assert sheq.value_availability == ValueAvailability.PRESENT
    assert sheq.value == Decimal("-1000000")
    assert eqar.value_availability == ValueAvailability.PRESENT
    assert eqar.value == Decimal("-0.02")


def test_zero_total_assets_remains_present_not_missing() -> None:
    _, metrics = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    ta = next(m for m in metrics if m.envelope_id == "ENV_8056_20240520001" and m.metric_type == "total_assets")
    assert ta.value_availability == ValueAvailability.PRESENT
    assert ta.value == Decimal("0")
    assert ta.value is not None


def test_missing_stock_metric_field_is_missing_or_unspecified() -> None:
    """TA/ShEq/EqAR自体がRaw Payloadに存在しないDisclosure(ENV_7203_20240809001)
    では、NOT_APPLICABLEではなくMISSING_OR_UNSPECIFIEDとして扱う。"""
    _, metrics = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    for metric_type in ("total_assets", "provider_reported_sheq", "provider_reported_eqar"):
        m = next(x for x in metrics if x.envelope_id == "ENV_7203_20240809001" and x.metric_type == metric_type)
        assert m.value_availability == ValueAvailability.MISSING_OR_UNSPECIFIED
        assert m.value is None


def test_eqar_validation_against_sheq_over_ta_does_not_overwrite_provider_value() -> None:
    """§10: EqAR ≈ ShEq/TAはValidation目的の確認に限定し、Lab側で計算した値で
    Provider供給のEqARを上書きしない(Primary ValueはRaw provider EqARのまま)。"""
    _, metrics = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    ta = next(m for m in metrics if m.envelope_id == "ENV_7203_20241101001" and m.metric_type == "total_assets")
    sheq = next(m for m in metrics if m.envelope_id == "ENV_7203_20241101001" and m.metric_type == "provider_reported_sheq")
    eqar = next(m for m in metrics if m.envelope_id == "ENV_7203_20241101001" and m.metric_type == "provider_reported_eqar")

    assert ta.value is not None
    assert sheq.value is not None
    assert eqar.value is not None
    # Validationのみ: ShEq/TAの比率がProvider EqARと概ね丸め整合することを確認する
    # (実データ2024-11-06 2Qで確認済みのパターン、D0081)。
    computed_ratio = sheq.value / ta.value
    assert abs(computed_ratio - eqar.value) < Decimal("0.001")
    # Provider供給の値そのものがraw_value/valueとして保持されていること(Lab側の
    # 再計算結果で上書きされていないこと)を確認する。
    assert eqar.raw_value == "0.385"
    assert eqar.value == Decimal("0.385")


# --- 決定性(Reproducibility): 同じRaw Payload -> 同じ結果 ---


def test_parsing_is_deterministic_across_runs() -> None:
    payload = _load_payload()
    envelopes_1, metrics_1 = parse_financial_summary_payload(payload, retrieved_at=_RETRIEVED_AT)
    envelopes_2, metrics_2 = parse_financial_summary_payload(payload, retrieved_at=_RETRIEVED_AT)
    assert [e.envelope_id for e in envelopes_1] == [e.envelope_id for e in envelopes_2]
    assert [(m.metric_id, m.value, m.value_availability) for m in metrics_1] == [
        (m.metric_id, m.value, m.value_availability) for m in metrics_2
    ]
