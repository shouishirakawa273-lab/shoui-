"""Step 3(2026-11-24): DocType登録とField追加のテスト。実APIには接続しない。

**行の形と値は2026-11-24の実観測から取っている**(7203と89510を
`scripts/jquants_step3_schema_diagnostic.py` で観測した結果、
`JQUANTS_V2_STEP3_SOURCE_ONBOARDING.md` §16)。合成データで機構だけを試して
意味を試さない、という今週の反省を踏まえ、値は実際に返ってきたものを使う。

7203は2017〜2020年が米国基準、2021年以降がIFRS。89510(日本ビルファンド)は
REITで、`ShEq`が空・`Eq`のみ、`DivAnn`が空・`DivUnit`のみ、`OdP`は入っている。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from lib.evidence.model import ValueAvailability
from lib.fundamentals.model import ActualOrForecast, ConsolidationScope, FiscalYearTarget, PeriodBasis
from lib.fundamentals.normalize import (
    ACCOUNTING_STANDARD_IFRS,
    ACCOUNTING_STANDARD_JMIS,
    ACCOUNTING_STANDARD_PROVIDER_SUFFIX_JP,
    ACCOUNTING_STANDARD_USGAAP,
    parse_financial_summary_payload,
)

RETRIEVED_AT = datetime(2026, 11, 24, tzinfo=UTC)


def _row(**overrides: Any) -> dict[str, Any]:
    """7203の2026-05-08 FY開示を骨格にした1行。空文字列は実データどおり空のまま。"""
    row: dict[str, Any] = {
        "Code": "72030",
        "DiscNo": "20260508500001",
        "DiscDate": "2026-05-08",
        "DiscTime": "13:55",
        "DocType": "FYFinancialStatements_Consolidated_IFRS",
        "CurPerType": "FY",
        "CurFYSt": "2025-04-01",
        "CurFYEn": "2026-03-31",
        "CurPerSt": "2025-04-01",
        "CurPerEn": "2026-03-31",
        "NxtFYSt": "2026-04-01",
        "NxtFYEn": "2027-03-31",
        "Sales": "50684952000000",
        "OP": "3766216000000",
        "OdP": "",
        "NP": "3848098000000",
        "EPS": "295.25",
        "BPS": "3062.82",
        "ShEq": "39918854000000",
        "Eq": "41000000000000",
        "ROE": "0.101",
        "ShOutFY": "16300000000",
        "TrShFY": "1200000000",
        "AvgSh": "13030000000",
        "DivAnn": "95",
        "FDivAnn": "100",
        "NxFDivAnn": "",
        "PayoutRatioAnn": "0.322",
        "DivUnit": "",
        "FDivUnit": "",
    }
    row.update(overrides)
    return row


def _reit_row(**overrides: Any) -> dict[str, Any]:
    """89510の観測形状。`ShEq`/`AvgSh`/`DivAnn`が空、`Eq`/`DivUnit`/`OdP`が入る。"""
    row = _row(
        Code="89510",
        DocType="FYFinancialStatements_Consolidated_REIT",
        CurFYSt="2026-01-01",
        CurFYEn="2026-06-30",
        CurPerSt="2026-01-01",
        CurPerEn="2026-06-30",
        NxtFYSt="2026-07-01",
        NxtFYEn="2026-12-31",
        OdP="38000000000",
        ShEq="",
        Eq="700000000000",
        AvgSh="",
        DivAnn="",
        FDivAnn="",
        PayoutRatioAnn="",
        DivUnit="11500",
        BPS="420000",
        ROE="0.021",
    )
    row.update(overrides)
    return row


def _metric(metrics: Any, metric_type: str) -> Any:
    found = [m for m in metrics if m.metric_type == metric_type]
    assert len(found) == 1, f"{metric_type}: {len(found)}件"
    return found[0]


# --- DocType -> 会計基準 ---


@pytest.mark.parametrize(
    ("doc_type", "expected"),
    [
        ("FYFinancialStatements_Consolidated_US", ACCOUNTING_STANDARD_USGAAP),
        ("1QFinancialStatements_Consolidated_US", ACCOUNTING_STANDARD_USGAAP),
        ("2QFinancialStatements_Consolidated_US", ACCOUNTING_STANDARD_USGAAP),
        ("3QFinancialStatements_Consolidated_US", ACCOUNTING_STANDARD_USGAAP),
        ("FYFinancialStatements_Consolidated_IFRS", ACCOUNTING_STANDARD_IFRS),
        ("FYFinancialStatements_NonConsolidated_IFRS", ACCOUNTING_STANDARD_IFRS),
        ("OtherPeriodFinancialStatements_Consolidated_IFRS", ACCOUNTING_STANDARD_IFRS),
        ("FYFinancialStatements_Consolidated_JP", ACCOUNTING_STANDARD_PROVIDER_SUFFIX_JP),
        ("FYFinancialStatements_NonConsolidated_JP", ACCOUNTING_STANDARD_PROVIDER_SUFFIX_JP),
        ("FYFinancialStatements_Consolidated_JMIS", ACCOUNTING_STANDARD_JMIS),
    ],
)
def test_registered_doc_types_resolve(doc_type: str, expected: str) -> None:
    envelopes, _ = parse_financial_summary_payload([_row(DocType=doc_type)], retrieved_at=RETRIEVED_AT)
    assert envelopes[0].accounting_standard == expected


def test_us_doc_type_no_longer_fails_closed() -> None:
    """[回帰] 7203の2017〜2020年が `accounting_standard=None` になっていた原因。"""
    envelopes, _ = parse_financial_summary_payload(
        [_row(DocType="FYFinancialStatements_Consolidated_US")], retrieved_at=RETRIEVED_AT
    )
    assert envelopes[0].accounting_standard is not None


def test_jmis_is_not_folded_into_ifrs() -> None:
    """ＪＭＩＳは修正国際基準。IFRSベースだが別の会計基準である。"""
    envelopes, _ = parse_financial_summary_payload(
        [_row(DocType="FYFinancialStatements_Consolidated_JMIS")], retrieved_at=RETRIEVED_AT
    )
    assert envelopes[0].accounting_standard == ACCOUNTING_STANDARD_JMIS
    assert envelopes[0].accounting_standard != ACCOUNTING_STANDARD_IFRS


@pytest.mark.parametrize(
    "doc_type",
    [
        "FYFinancialStatements_Consolidated_REIT",
        "FYFinancialStatements_Consolidated_Foreign",
        "FYFinancialStatements_NonConsolidated_Foreign",
        "REITEarnForecastRevision",
        "EarnForecastRevision",
        "DividendForecastRevision",
    ],
)
def test_issuer_category_doc_types_stay_unknown(doc_type: str) -> None:
    """REIT・外国株は発行者区分で会計基準ではない。推測でマップしない。"""
    envelopes, _ = parse_financial_summary_payload([_row(DocType=doc_type)], retrieved_at=RETRIEVED_AT)
    assert envelopes[0].accounting_standard is None


def test_known_non_standard_doc_type_is_not_a_warning(caplog: pytest.LogCaptureFixture) -> None:
    """仕様どおりの既知の状態。調査すべき異常のwarningに埋もれさせない。"""
    with caplog.at_level(logging.INFO, logger="lib.fundamentals.normalize"):
        parse_financial_summary_payload([_row(DocType="FYFinancialStatements_Consolidated_REIT")], retrieved_at=RETRIEVED_AT)
    levels = {r.levelno for r in caplog.records if "REIT" in r.getMessage()}
    assert logging.INFO in levels
    assert logging.WARNING not in levels


def test_genuinely_unknown_doc_type_still_warns(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="lib.fundamentals.normalize"):
        parse_financial_summary_payload([_row(DocType="SomethingNewFromTheProvider")], retrieved_at=RETRIEVED_AT)
    assert any(r.levelno == logging.WARNING for r in caplog.records)


# --- 経常利益のNOT_APPLICABLE ---


def test_ordinary_profit_is_not_applicable_under_usgaap() -> None:
    """[回帰] 7203の41行すべてで `OdP` が空だった。米国基準にも経常利益はない。"""
    _, metrics = parse_financial_summary_payload(
        [_row(DocType="FYFinancialStatements_Consolidated_US", OdP="")], retrieved_at=RETRIEVED_AT
    )
    assert _metric(metrics, "ordinary_profit").value_availability is ValueAvailability.NOT_APPLICABLE


def test_reit_ordinary_profit_is_present_not_not_applicable() -> None:
    """REITは経常利益を開示している(89510: OdP 20/27)。NOT_APPLICABLEにしない。"""
    _, metrics = parse_financial_summary_payload([_reit_row()], retrieved_at=RETRIEVED_AT)
    odp = _metric(metrics, "ordinary_profit")
    assert odp.value_availability is ValueAvailability.PRESENT
    assert odp.value_availability is not ValueAvailability.NOT_APPLICABLE


def test_jmis_ordinary_profit_is_not_assumed_absent() -> None:
    """JMISについて公式記載がないので、NOT_APPLICABLEと決めつけない。"""
    _, metrics = parse_financial_summary_payload(
        [_row(DocType="FYFinancialStatements_Consolidated_JMIS", OdP="")], retrieved_at=RETRIEVED_AT
    )
    assert _metric(metrics, "ordinary_profit").value_availability is not ValueAvailability.NOT_APPLICABLE


# --- 新規Field ---


def test_roe_is_mapped_with_the_observed_value() -> None:
    _, metrics = parse_financial_summary_payload([_row()], retrieved_at=RETRIEVED_AT)
    roe = _metric(metrics, "provider_reported_roe")
    assert roe.value == Decimal("0.101")
    assert roe.value_availability is ValueAvailability.PRESENT
    assert roe.actual_or_forecast is ActualOrForecast.ACTUAL
    assert roe.period_basis is PeriodBasis.CUMULATIVE


def test_bps_is_mapped_as_a_point_in_time_stock() -> None:
    _, metrics = parse_financial_summary_payload([_row()], retrieved_at=RETRIEVED_AT)
    bps = _metric(metrics, "bps")
    assert bps.value == Decimal("3062.82")
    assert bps.period_basis is PeriodBasis.POINT_IN_TIME


def test_share_counts_are_kept_separate_and_not_subtracted() -> None:
    """`ShOutFY - TrShFY` は公式が示す導出だが、normalize.pyでは計算しない。"""
    _, metrics = parse_financial_summary_payload([_row()], retrieved_at=RETRIEVED_AT)
    assert _metric(metrics, "shares_outstanding_period_end").value == Decimal("16300000000")
    assert _metric(metrics, "treasury_shares_period_end").value == Decimal("1200000000")
    assert not [m for m in metrics if "ex_treasury" in m.metric_type]


def test_sheq_and_eq_are_distinct_metrics() -> None:
    """自己資本と純資産は別概念。値が違うので統合しない。"""
    _, metrics = parse_financial_summary_payload([_row()], retrieved_at=RETRIEVED_AT)
    sheq = _metric(metrics, "provider_reported_sheq")
    eq = _metric(metrics, "provider_reported_eq")
    assert sheq.value != eq.value
    assert sheq.series_id != eq.series_id


def test_dividend_per_share_and_distribution_per_unit_are_distinct() -> None:
    """一株当たり配当と1口当たり分配金は別概念。読み替えない。"""
    _, metrics = parse_financial_summary_payload([_row()], retrieved_at=RETRIEVED_AT)
    assert _metric(metrics, "dividend_per_share_annual").value == Decimal("95")
    assert _metric(metrics, "distribution_per_unit").value_availability is ValueAvailability.MISSING_OR_UNSPECIFIED


def test_dividend_forecast_targets_the_right_fiscal_year() -> None:
    _, metrics = parse_financial_summary_payload([_row()], retrieved_at=RETRIEVED_AT)
    current = _metric(metrics, "dividend_per_share_annual_current_year_forecast")
    following = _metric(metrics, "dividend_per_share_annual_next_year_forecast")
    assert current.fiscal_year_target is FiscalYearTarget.CURRENT_FISCAL_YEAR
    assert current.actual_or_forecast is ActualOrForecast.COMPANY_FORECAST
    assert following.fiscal_year_target is FiscalYearTarget.NEXT_FISCAL_YEAR
    assert following.value_availability is ValueAvailability.MISSING_OR_UNSPECIFIED


def test_non_consolidated_fields_carry_non_consolidated_scope() -> None:
    _, metrics = parse_financial_summary_payload(
        [_row(NCShEq="1000", NCEq="1100", NCROE="0.05", NCBPS="900")], retrieved_at=RETRIEVED_AT
    )
    for metric_type in (
        "provider_reported_sheq_non_consolidated",
        "provider_reported_eq_non_consolidated",
        "provider_reported_roe_non_consolidated",
        "bps_non_consolidated",
    ):
        assert _metric(metrics, metric_type).consolidation_scope is ConsolidationScope.NON_CONSOLIDATED


# --- REITの観測形状 ---


def test_reit_row_yields_eq_and_distribution_but_not_sheq_or_dividend() -> None:
    """[回帰] REITのBPS系を`ShEq`経由で組むと全て取得不可になる。"""
    _, metrics = parse_financial_summary_payload([_reit_row()], retrieved_at=RETRIEVED_AT)
    assert _metric(metrics, "provider_reported_sheq").value_availability is ValueAvailability.MISSING_OR_UNSPECIFIED
    assert _metric(metrics, "provider_reported_eq").value == Decimal("700000000000")
    assert _metric(metrics, "distribution_per_unit").value == Decimal("11500")
    assert _metric(metrics, "dividend_per_share_annual").value_availability is ValueAvailability.MISSING_OR_UNSPECIFIED
    assert _metric(metrics, "average_shares").value_availability is ValueAvailability.MISSING_OR_UNSPECIFIED


def test_reit_still_yields_roe_and_bps() -> None:
    _, metrics = parse_financial_summary_payload([_reit_row()], retrieved_at=RETRIEVED_AT)
    assert _metric(metrics, "provider_reported_roe").value == Decimal("0.021")
    assert _metric(metrics, "bps").value == Decimal("420000")


def test_empty_value_is_missing_not_zero() -> None:
    """Unknownは0ではない。空文字列を0扱いしない。"""
    _, metrics = parse_financial_summary_payload([_row(ROE="", BPS="")], retrieved_at=RETRIEVED_AT)
    for metric_type in ("provider_reported_roe", "bps"):
        metric = _metric(metrics, metric_type)
        assert metric.value is None
        assert metric.value != Decimal(0)
        assert metric.value_availability is ValueAvailability.MISSING_OR_UNSPECIFIED
