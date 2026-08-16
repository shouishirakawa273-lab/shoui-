"""Phase4A(D0043 追記): 2026-08-16 Local Real Data Validation(7203)で確認した
実Wire Formatの型変換・Coverage Semanticsに関するテスト。

実際のRaw Responseで確認済みの事実(ユーザー報告):

    Sales      = "15481299000000"   # 大きな整数値も文字列
    EPS        = "109.28"           # 小数値も文字列
    OdP        = ""                 # 欠損値は空文字列
    MatChgSub  = "false"            # boolean的な値も文字列

これらはWire上ではすべて文字列として返るため、Numeric/Decimal/BooleanへのParseは
Normalized Layerでのみ厳格に行う。Rawはそのまま保持する(既存方針)。
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from lib.evidence.model import ValueAvailability
from lib.fundamentals.normalize import (
    ACCOUNTING_STANDARD_IFRS,
    ACCOUNTING_STANDARD_PROVIDER_SUFFIX_JP,
    parse_boolean_string,
    parse_financial_summary_payload,
    raw_disclosure_date_range,
)

_FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "financial_summary_v2.json"
_RETRIEVED_AT = datetime(2026, 1, 1, tzinfo=UTC)


def _load_payload() -> list[dict[str, object]]:
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))["data"]


# --- Numeric string(大きな整数値) -> 正しい数値型(実観測値、D0043追記) ---


def test_large_integer_like_numeric_string_parses_to_exact_decimal() -> None:
    """実観測: 7203のSales="15481299000000"。floatでは精度が失われうるため
    Decimalで厳密にParseする。"""
    _, metrics = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    toyota_sales = next(m for m in metrics if m.envelope_id == "ENV_7203_20240510001" and m.metric_type == "sales")
    assert toyota_sales.raw_value == "15481299000000"
    assert toyota_sales.value == Decimal("15481299000000")
    assert toyota_sales.value_availability == ValueAvailability.PRESENT


# --- Decimal string(小数値) -> Decimal(実観測値、D0043追記) ---


def test_decimal_numeric_string_parses_to_exact_decimal() -> None:
    """実観測: 7203のEPS="109.28"。"""
    _, metrics = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    toyota_eps = next(m for m in metrics if m.envelope_id == "ENV_7203_20240510001" and m.metric_type == "eps")
    assert toyota_eps.raw_value == "109.28"
    assert toyota_eps.value == Decimal("109.28")
    assert toyota_eps.value_availability == ValueAvailability.PRESENT


# --- Boolean-like string(明示的literalのみ受理、Python truthiness禁止) ---


def test_parse_boolean_string_accepts_only_explicit_literals() -> None:
    assert parse_boolean_string("true") is True
    assert parse_boolean_string("false") is False


def test_parse_boolean_string_unknown_literal_fails_closed_to_none() -> None:
    """未知literal(大文字/数値/空文字列等)はUNKNOWN(None)へfail closedする。
    `bool("false")`のようなPython truthinessは使わない(それだとTrueになってしまう)。"""
    assert parse_boolean_string("False") is None  # 大文字小文字違いも安易に受理しない
    assert parse_boolean_string("1") is None
    assert parse_boolean_string("0") is None
    assert parse_boolean_string("") is None
    assert parse_boolean_string(None) is None
    assert bool("false") is True  # 参考: これがPython truthinessの罠(このLabでは使わない)


def test_observed_mat_chg_sub_false_string_parses_correctly() -> None:
    """実観測: 7203のMatChgSub="false"。"""
    assert parse_boolean_string("false") is False


# --- Empty String Semantics: ""は0でもFalseでもない ---


def test_empty_string_is_not_equal_to_zero_or_false() -> None:
    assert "" != 0
    assert "" != False  # noqa: E712  (意図的にFalseとの非等価性を確認する)
    assert ValueAvailability.MISSING_OR_UNSPECIFIED != 0
    assert ValueAvailability.MISSING_OR_UNSPECIFIED != False  # noqa: E712


def test_empty_field_default_is_missing_or_unspecified() -> None:
    """会計基準から確認できない空値の既定はMISSING_OR_UNSPECIFIED(NOT_APPLICABLEへの
    昇格は確認できる場合のみ、D0043)。"""
    _, metrics = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    toyota_next_sales = next(
        m for m in metrics if m.envelope_id == "ENV_7203_20240510001" and m.metric_type == "sales_next_year_forecast"
    )
    assert toyota_next_sales.raw_value == ""  # NxFSalesはFixture上、明示的に空文字列
    assert toyota_next_sales.value_availability == ValueAvailability.MISSING_OR_UNSPECIFIED
    assert toyota_next_sales.value is None


# --- IFRS OdP(経常利益)のNOT_APPLICABLE判定(実確認済みDocTypeで再確認) ---


def test_ifrs_ordinary_profit_not_applicable_with_confirmed_real_doc_type() -> None:
    """DocType="FYFinancialStatements_Consolidated_IFRS"(Local Real Data
    Validationで実在確認済み、_SYNTHサフィックス無し)でもNOT_APPLICABLE判定が
    機能することを確認する。"""
    envelopes, metrics = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    sony = next(e for e in envelopes if e.internal_code == "6758")
    assert sony.document_type == "FYFinancialStatements_Consolidated_IFRS"
    assert sony.accounting_standard == "IFRS"
    sony_odp = next(m for m in metrics if m.envelope_id == sony.envelope_id and m.metric_type == "ordinary_profit")
    assert sony_odp.raw_value == ""
    assert sony_odp.value_availability == ValueAvailability.NOT_APPLICABLE
    assert sony_odp.value is None
    assert sony_odp.value != 0


# --- DiscNoからDisclosure Dateを推測しない(実観測の不一致ケース、D0043追記) ---


def test_disc_no_is_not_used_to_derive_disclosure_date() -> None:
    """実観測: DiscNo=20220204580837(先頭が2022-02-04を思わせる)だが
    DiscDate=2022-02-09(実際の開示日は異なる)。DiscNoは不透明な文字列として
    保持するのみで、日付Parseには一切使わない。"""
    payload = [
        {
            "Code": "99990",
            "DiscNo": "20220204580837",
            "DocType": "SYNTH_DOC_TYPE",
            "DiscDate": "2022-02-09",
            "DiscTime": "15:00",
            "CurPerType": "FY",
            "Sales": "1",
        }
    ]
    envelopes, _ = parse_financial_summary_payload(payload, retrieved_at=_RETRIEVED_AT)
    envelope = envelopes[0]
    assert envelope.disclosure_number == "20220204580837"
    assert envelope.disclosure_date == date(2022, 2, 9)
    assert envelope.market_public_at is not None
    assert envelope.market_public_at.date() == date(2022, 2, 9)  # DiscNoの数字部分(2022-02-04)ではない


# --- Raw Coverage != Requested Research Window ---


def test_raw_disclosure_date_range_reflects_actual_payload_not_requested_window() -> None:
    """実観測: --start/--end=2024-01-01/2024-12-31を指定しても、Rawには
    2021-11-04〜2026-08-04の範囲が返った(D0043追記)。この関数はPayloadの
    実際の範囲のみを機械的に返し、Research Windowによる絞り込みは行わない。"""
    payload = [
        {"Code": "72030", "DiscDate": "2021-11-04", "DiscTime": "15:00", "CurPerType": "2Q", "Sales": "1"},
        {"Code": "72030", "DiscDate": "2024-05-10", "DiscTime": "15:00", "CurPerType": "FY", "Sales": "1"},
        {"Code": "72030", "DiscDate": "2026-08-04", "DiscTime": "15:00", "CurPerType": "1Q", "Sales": "1"},
    ]
    raw_min, raw_max = raw_disclosure_date_range(payload)
    assert raw_min == date(2021, 11, 4)
    assert raw_max == date(2026, 8, 4)
    # Requested Research Windowが2024年のみでも、Raw Coverageはそれを超えてよい(異常ではない)。
    requested_start, requested_end = date(2024, 1, 1), date(2024, 12, 31)
    assert raw_min < requested_start
    assert raw_max > requested_end


def test_raw_disclosure_date_range_ignores_rows_without_parseable_disc_date() -> None:
    payload = [
        {"Code": "72030", "DiscDate": "", "Sales": "1"},
        {"Code": "72030", "Sales": "1"},  # DiscDateキー自体が無い
        {"Code": "72030", "DiscDate": "not-a-date", "Sales": "1"},
        {"Code": "72030", "DiscDate": "2024-05-10", "Sales": "1"},
    ]
    raw_min, raw_max = raw_disclosure_date_range(payload)
    assert raw_min == raw_max == date(2024, 5, 10)


def test_raw_disclosure_date_range_returns_none_when_no_valid_dates() -> None:
    assert raw_disclosure_date_range([]) == (None, None)
    assert raw_disclosure_date_range([{"Code": "72030"}]) == (None, None)


# --- "_JP"接尾辞DocType(4銘柄Local Real Data Validation、3626で確認済み) ---


def test_jp_suffix_doc_type_is_recognized_not_fail_closed_to_unknown(caplog: pytest.LogCaptureFixture) -> None:
    """3626(TIS)の実DocType"2QFinancialStatements_Consolidated_JP"は既知の
    DocTypeとしてMappingされ、未知DocType警告(fail closed)は発生しない。"""
    with caplog.at_level("WARNING"):
        envelopes, _ = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    tis = next(e for e in envelopes if e.envelope_id == "ENV_3626_20240525001")
    assert tis.document_type == "2QFinancialStatements_Consolidated_JP"
    assert tis.accounting_standard is not None
    assert "2QFinancialStatements_Consolidated_JP" not in caplog.text


def test_jp_suffix_doc_type_maps_to_neutral_label_not_ifrs_and_not_jgaap() -> None:
    """ "_JP"接尾辞の公式な意味(JGAAPと同義か等)は未確認のため、"JGAAP"という
    名称は採用しない。IFRSとは区別できる、中立的な識別子を使う(D0043追記)。"""
    envelopes, _ = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    tis = next(e for e in envelopes if e.envelope_id == "ENV_3626_20240525001")
    assert tis.accounting_standard == ACCOUNTING_STANDARD_PROVIDER_SUFFIX_JP
    assert tis.accounting_standard != ACCOUNTING_STANDARD_IFRS
    assert tis.accounting_standard != "JGAAP"


def test_jp_suffix_accounting_standard_distinct_from_ifrs_accounting_standard() -> None:
    """3626("_JP")と6758("_IFRS")のaccounting_standardは異なる値になる。"""
    envelopes, _ = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    tis = next(e for e in envelopes if e.internal_code == "3626")
    sony = next(e for e in envelopes if e.internal_code == "6758")
    assert tis.accounting_standard != sony.accounting_standard
    assert sony.accounting_standard == ACCOUNTING_STANDARD_IFRS


def test_jp_suffix_accounting_standard_not_registered_as_ordinary_profit_not_applicable() -> None:
    """ "_JP"接尾辞について経常利益がNOT_APPLICABLEになるという事実は確認できて
    いないため、_NOT_APPLICABLE_UNDER_STANDARDへは登録しない(未確認事項を
    推測で埋めない、D0043追記)。"""
    _, metrics = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    tis_odp = next((m for m in metrics if m.envelope_id == "ENV_3626_20240525001" and m.metric_type == "ordinary_profit"), None)
    assert tis_odp is not None
    # TIS Fixture行にOdPフィールド自体が無いためraw_value=None -> MISSING_OR_UNSPECIFIED
    # (会計基準から確認できない空値の既定、NOT_APPLICABLEへの誤った昇格ではない)。
    assert tis_odp.value_availability == ValueAvailability.MISSING_OR_UNSPECIFIED


# --- Provider Schema Evolution: 未知Fieldは引き続きRawで保持される(念のため再確認) ---


def test_boolean_and_new_wire_fields_do_not_break_normalizer() -> None:
    """MatChgSub/SigChgInC/RetroRst/BPS等、Metricへ未マッピングのFieldが
    payloadに含まれていてもNormalizerは壊れない(既存のProvider Schema
    Evolution前方互換方針の再確認、D0043追記)。"""
    envelopes, metrics = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    toyota_first = next(e for e in envelopes if e.envelope_id == "ENV_7203_20240510001")
    assert toyota_first.internal_code == "7203"
    assert len([m for m in metrics if m.envelope_id == toyota_first.envelope_id]) > 0
