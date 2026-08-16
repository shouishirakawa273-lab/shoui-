"""Phase4A(D0043): Financial Summary Normalizerのテスト。

`13_tests/fixtures/financial_summary_v2.json`(J-Quants V2 `/v2/fins/summary`の
生レスポンス形状を模したGolden Fixture、合成データ)を使う。Field名は全て未検証
(DECISIONS.md D0043参照)。
"""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
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


def test_period_basis_is_always_cumulative_never_derived_standalone() -> None:
    """Phase4AはProviderの値をそのまま保持するのみで、2Q累計からQ2単独値を
    計算する導出は行わない(period_basisは常にCUMULATIVE)。"""
    _, metrics = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    assert all(m.period_basis == PeriodBasis.CUMULATIVE for m in metrics)
    assert not any(m.period_basis == PeriodBasis.STANDALONE for m in metrics)


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


# --- 決定性(Reproducibility): 同じRaw Payload -> 同じ結果 ---


def test_parsing_is_deterministic_across_runs() -> None:
    payload = _load_payload()
    envelopes_1, metrics_1 = parse_financial_summary_payload(payload, retrieved_at=_RETRIEVED_AT)
    envelopes_2, metrics_2 = parse_financial_summary_payload(payload, retrieved_at=_RETRIEVED_AT)
    assert [e.envelope_id for e in envelopes_1] == [e.envelope_id for e in envelopes_2]
    assert [(m.metric_id, m.value, m.value_availability) for m in metrics_1] == [
        (m.metric_id, m.value, m.value_availability) for m in metrics_2
    ]
