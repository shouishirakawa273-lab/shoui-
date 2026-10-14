"""`lib.global_market.normalize`/`view`/`evidence`のPIT Test(Phase4E-1)。
Test IDはユーザーTask仕様のGLOBAL-*に対応する(期待値はPhase4E-1要件から
導出、実装からのコピーではない)。normalize.pyはSource非依存のため、この
Roundで実装した具体的Adapterが無くても、Test内で明示的な`resolve_
available_at`Callbackを注入して原則を検証できる。
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from lib.evidence.model import AvailabilityBasis, DataLayer, Frequency, ValueAvailability, filter_usable_at
from lib.global_market.evidence import global_market_record_to_evidence
from lib.global_market.model import GlobalMarketRecord, IndexReturnType, InstrumentCategory
from lib.global_market.normalize import build_revision_histories
from lib.global_market.view import global_market_as_of
from lib.sources.catalog import SourceAuthorityClass

RETRIEVED_AT_UTC = datetime(2026, 8, 19, 6, 0, tzinfo=UTC)
US_CLOSE_TIME = (16, 0)  # 16:00 US Eastern(NYSE通常大引け、架空の確認済み値)


def _record(
    *,
    record_id: str,
    series_id: str = "SPX_PRICE_INDEX:PROVIDER:DAILY:2026-08-18",
    session_date: date = date(2026, 8, 18),
    market_timezone: str = "America/New_York",
    value: str = "5000.12",
    retrieved_at: datetime = RETRIEVED_AT_UTC,
) -> GlobalMarketRecord:
    return GlobalMarketRecord(
        record_id=record_id,
        series_id=series_id,
        instrument_category=InstrumentCategory.EQUITY_INDEX,
        index_return_type=IndexReturnType.PRICE_RETURN,
        metric_name="SPX_PRICE_INDEX",
        source_id="PROVIDER",
        frequency=Frequency.DAILY,
        session_date=session_date,
        market_timezone=market_timezone,
        raw_value=value,
        value=Decimal(value),
        unit="index points",
        value_availability=ValueAvailability.PRESENT,
        retrieved_at=retrieved_at,
        normalizer_version="TEST_V1",
    )


def _us_close_resolver(record: GlobalMarketRecord) -> tuple[datetime, AvailabilityBasis]:
    """Test専用Resolver: `market_timezone`をZoneInfoで解決し、Session当日の
    大引け時刻(16:00 Local)をavailable_atとする(DST-safe、固定Offsetでは
    ない)。"""
    hour, minute = US_CLOSE_TIME
    tz = ZoneInfo(record.market_timezone)
    close_at = datetime(
        record.session_date.year,
        record.session_date.month,
        record.session_date.day,
        hour,
        minute,
        tzinfo=tz,
    )
    return close_at, AvailabilityBasis.INFERRED


# --- GLOBAL-001: Future US Session Leakage ---


def test_global001_japan_morning_cannot_see_same_day_us_close() -> None:
    """日本時間8/18 10:00時点では、同日8/18のUS Closeはまだ発生していない
    (US Close=8/18 16:00 ET=8/19早朝JST)。"""
    record = _record(record_id="R1", session_date=date(2026, 8, 18))
    histories = build_revision_histories([record], resolve_available_at=_us_close_resolver)
    japan_morning = datetime(2026, 8, 18, 10, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    result = global_market_as_of(histories, japan_morning)
    assert result[record.series_id] is None


def test_global001_japan_next_morning_can_see_prior_day_us_close() -> None:
    record = _record(record_id="R1", session_date=date(2026, 8, 18))
    histories = build_revision_histories([record], resolve_available_at=_us_close_resolver)
    # 8/18 16:00 EDT(UTC-4) = 8/19 05:00 JST。8/19 07:00 JSTなら利用可能なはず。
    japan_next_morning = datetime(2026, 8, 19, 7, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    result = global_market_as_of(histories, japan_next_morning)
    assert result[record.series_id] is not None
    assert result[record.series_id].value == "5000.12"


# --- GLOBAL-002: Timezone Conversion ---


def test_global002_utc_and_jst_decision_at_agree_on_availability() -> None:
    """同じ瞬間をUTCとJSTで表現しても、Availability判定結果は一致する
    (Timezone変換が正しいことの確認)。"""
    record = _record(record_id="R1", session_date=date(2026, 8, 18))
    histories = build_revision_histories([record], resolve_available_at=_us_close_resolver)
    instant_utc = datetime(2026, 8, 19, 5, 30, tzinfo=UTC)
    instant_jst = instant_utc.astimezone(ZoneInfo("Asia/Tokyo"))
    assert global_market_as_of(histories, instant_utc) == global_market_as_of(histories, instant_jst)


# --- GLOBAL-003: DST Safety ---


def test_global003_fixed_utc_offset_would_be_wrong_across_dst_boundary() -> None:
    """US EasternのUTC Offsetは夏時間(EDT, UTC-4)と冬時間(EST, UTC-5)で
    異なる。固定Offsetを年間通して適用すると誤りになることを、実際に
    ZoneInfoで解決したTimestampのUTC Offsetが季節で変わることによって
    示す(Phase4E-1要件§10)。"""
    winter_record = _record(record_id="R_WINTER", session_date=date(2026, 1, 15))
    summer_record = _record(record_id="R_SUMMER", session_date=date(2026, 7, 15))
    winter_close, _ = _us_close_resolver(winter_record)
    summer_close, _ = _us_close_resolver(summer_record)
    assert winter_close.utcoffset() == timedelta(hours=-5)  # EST
    assert summer_close.utcoffset() == timedelta(hours=-4)  # EDT
    assert winter_close.utcoffset() != summer_close.utcoffset()


def test_global003_naive_market_timezone_string_rejected_by_zoneinfo() -> None:
    with pytest.raises(Exception, match=".*"):  # noqa: B017 -- ZoneInfoNotFoundError、無効なTimezone名を明示的に拒否することの確認
        ZoneInfo("NOT_A_REAL_TIMEZONE")


# --- GLOBAL-004: Session Date Is Not Availability ---


def test_global004_session_date_alone_does_not_make_record_usable() -> None:
    record = _record(record_id="R1", session_date=date(2026, 8, 18))
    histories = build_revision_histories([record], resolve_available_at=_us_close_resolver)
    same_day_before_close = datetime(2026, 8, 18, 10, 0, tzinfo=ZoneInfo("America/New_York"))
    result = global_market_as_of(histories, same_day_before_close)
    assert result[record.series_id] is None


# --- GLOBAL-005: Unknown Provider Availability ---


def test_global005_unknown_availability_basis_excluded_by_default() -> None:
    record = _record(record_id="R1")

    def _unknown_resolver(r: GlobalMarketRecord) -> tuple[datetime, AvailabilityBasis]:
        return r.retrieved_at, AvailabilityBasis.UNKNOWN

    histories = build_revision_histories([record], resolve_available_at=_unknown_resolver)
    far_future = datetime(2030, 1, 1, tzinfo=UTC)
    result = global_market_as_of(histories, far_future)
    assert result[record.series_id] is None


def test_global005_unknown_availability_included_only_when_explicit() -> None:
    record = _record(record_id="R1")

    def _unknown_resolver(r: GlobalMarketRecord) -> tuple[datetime, AvailabilityBasis]:
        return r.retrieved_at, AvailabilityBasis.UNKNOWN

    histories = build_revision_histories([record], resolve_available_at=_unknown_resolver)
    far_future = datetime(2030, 1, 1, tzinfo=UTC)
    result = global_market_as_of(histories, far_future, include_unknown_availability=True)
    assert result[record.series_id] is not None


# --- GLOBAL-006: FX Session Semantics(Equity Close Semanticsを強制しない) ---


def test_global006_fx_uses_provider_defined_timestamp_not_equity_close_convention() -> None:
    """FXは24h市場であり、Equity Close(16:00 Local)を強制しない
    ——`resolve_available_at`はSource固有であり、FX用のResolverはEquityと
    別に定義できることを確認する(Phase4E-1要件§14)。"""
    fx_record = GlobalMarketRecord(
        record_id="FX_1",
        series_id="USDJPY:PROVIDER:DAILY:2026-08-18",
        instrument_category=InstrumentCategory.FX,
        index_return_type=IndexReturnType.NOT_APPLICABLE,
        metric_name="USDJPY",
        source_id="PROVIDER",
        frequency=Frequency.DAILY,
        session_date=date(2026, 8, 18),
        market_timezone="UTC",  # FX Providerが独自に定義するReference Time(例: UTC 22:00)を想定
        raw_value="147.50",
        value=Decimal("147.50"),
        unit="JPY",
        currency="JPY",
        value_availability=ValueAvailability.PRESENT,
        retrieved_at=RETRIEVED_AT_UTC,
        normalizer_version="TEST_V1",
    )

    def _fx_resolver(r: GlobalMarketRecord) -> tuple[datetime, AvailabilityBasis]:
        # Equityの16:00 Local大引けとは全く異なるFX固有のReference Time(例: 22:00 UTC)を使う。
        fx_reference_at = datetime(r.session_date.year, r.session_date.month, r.session_date.day, 22, 0, tzinfo=UTC)
        return fx_reference_at, AvailabilityBasis.INFERRED

    histories = build_revision_histories([fx_record], resolve_available_at=_fx_resolver)
    result = global_market_as_of(histories, datetime(2026, 8, 18, 23, 0, tzinfo=UTC))
    assert result[fx_record.series_id] is not None


# --- GLOBAL-007: Index Identity ---


def test_global007_price_index_and_total_return_index_are_not_merged() -> None:
    price = _record(record_id="R_PRICE", series_id="SPX_PRICE:PROVIDER:DAILY:2026-08-18", value="5000.12")
    total_return = GlobalMarketRecord(
        record_id="R_TR",
        series_id="SPX_TOTAL_RETURN:PROVIDER:DAILY:2026-08-18",
        instrument_category=InstrumentCategory.EQUITY_INDEX,
        index_return_type=IndexReturnType.TOTAL_RETURN,
        metric_name="SPX_TOTAL_RETURN",
        source_id="PROVIDER",
        frequency=Frequency.DAILY,
        session_date=date(2026, 8, 18),
        market_timezone="America/New_York",
        raw_value="11000.55",
        value=Decimal("11000.55"),
        unit="index points",
        value_availability=ValueAvailability.PRESENT,
        retrieved_at=RETRIEVED_AT_UTC,
        normalizer_version="TEST_V1",
    )
    histories = build_revision_histories([price, total_return], resolve_available_at=_us_close_resolver)
    assert set(histories.keys()) == {price.series_id, total_return.series_id}
    assert histories[price.series_id].versions[0].value != histories[total_return.series_id].versions[0].value


# --- GLOBAL-008: Unit/Currency Preservation ---


def test_global008_currency_and_unit_are_not_conflated_across_series() -> None:
    index_record = _record(record_id="R_IDX")  # unit="index points", currency=None
    fx_record = GlobalMarketRecord(
        record_id="R_FX",
        series_id="USDJPY:PROVIDER:DAILY:2026-08-18",
        instrument_category=InstrumentCategory.FX,
        metric_name="USDJPY",
        source_id="PROVIDER",
        frequency=Frequency.DAILY,
        session_date=date(2026, 8, 18),
        market_timezone="UTC",
        raw_value="147.50",
        value=Decimal("147.50"),
        unit="JPY",
        currency="JPY",
        value_availability=ValueAvailability.PRESENT,
        retrieved_at=RETRIEVED_AT_UTC,
        normalizer_version="TEST_V1",
    )
    assert index_record.currency is None
    assert fx_record.currency == "JPY"
    assert index_record.unit != fx_record.unit


# --- GLOBAL-009: Future Injection ---


def test_global009_future_session_not_visible_to_past_as_of() -> None:
    future_record = _record(record_id="R_FUTURE", session_date=date(2030, 1, 1), value="9999")
    histories = build_revision_histories([future_record], resolve_available_at=_us_close_resolver)
    past_decision_at = datetime(2026, 8, 19, 7, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    result = global_market_as_of(histories, past_decision_at)
    assert result[future_record.series_id] is None


# --- GLOBAL-010: Raw Change Is Not Revision ---


def test_global010_raw_value_change_for_same_series_and_session_does_not_set_is_correction() -> None:
    """同一series_id・同一session_dateのRecordをRaw値違いで2回投入しても、
    `build_revision_histories()`は`is_correction`をTrueへ自動的に設定しない
    (RAW-002原則: Hash/値不一致からのRevision推測禁止)。skeptic-reviewer
    Finding(Phase4E-1): 従来のGLOBAL-010 Testは構造Import禁止のみを検証し、
    このRuleの実質的な検証になっていなかった。"""
    first = _record(record_id="R_FIRST", value="5000.12")
    second = _record(record_id="R_SECOND", value="5001.50")
    histories = build_revision_histories([first, second], resolve_available_at=_us_close_resolver)
    for version in histories[first.series_id].versions:
        assert version.is_correction is False


def test_global010_global_market_modules_never_import_document_relationship() -> None:
    import lib.global_market.evidence as evidence_module
    import lib.global_market.model as model_module
    import lib.global_market.normalize as normalize_module
    import lib.global_market.view as view_module

    for module in (model_module, normalize_module, view_module, evidence_module):
        source = module.__file__
        assert source is not None
        text = open(source, encoding="utf-8").read()
        assert "DocumentRelationship" not in text
        assert "DuplicateRelationKind" not in text


# --- GLOBAL-011: Determinism ---


def test_global011_same_input_produces_same_output() -> None:
    record = _record(record_id="R1")
    histories_a = build_revision_histories([record], resolve_available_at=_us_close_resolver)
    histories_b = build_revision_histories([record], resolve_available_at=_us_close_resolver)
    decision_at = datetime(2026, 8, 19, 7, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    result_a = global_market_as_of(histories_a, decision_at)
    result_b = global_market_as_of(histories_b, decision_at)
    assert result_a[record.series_id].value == result_b[record.series_id].value
    assert result_a[record.series_id].available_at == result_b[record.series_id].available_at


# --- GLOBAL-012: No Investment Interpretation ---


def test_global012_evidence_content_has_no_interpretive_language() -> None:
    record = _record(record_id="R1")
    evidence = global_market_record_to_evidence(
        record,
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        originating_source="PROVIDER",
        delivery_provider="PROVIDER",
    )
    forbidden_terms = (
        "bullish",
        "bearish",
        "buy",
        "sell",
        "risk-on",
        "risk-off",
        "好調",
        "悪化",
        "強気",
        "弱気",
        "輸出株",
        "資源株",
    )
    for term in forbidden_terms:
        assert term not in evidence.content.lower(), f"Evidence Contentに解釈語 '{term}' が含まれています"


# --- GLOBAL-013: Missing Is Not Zero ---


def test_global013_missing_raw_value_does_not_become_zero_in_source_version() -> None:
    record = _record(record_id="R1")
    missing_record = GlobalMarketRecord(
        record_id="R_MISSING",
        series_id=record.series_id,
        instrument_category=record.instrument_category,
        index_return_type=record.index_return_type,
        metric_name=record.metric_name,
        source_id=record.source_id,
        frequency=record.frequency,
        session_date=record.session_date,
        market_timezone=record.market_timezone,
        raw_value=None,
        value=None,
        unit=record.unit,
        value_availability=ValueAvailability.MISSING_OR_UNSPECIFIED,
        retrieved_at=RETRIEVED_AT_UTC,
        normalizer_version="TEST_V1",
    )
    histories = build_revision_histories([missing_record], resolve_available_at=_us_close_resolver)
    version = histories[record.series_id].versions[0]
    assert version.value == ""
    assert version.value != "0"


# --- GLOBAL-014: Naive Datetime Rejected ---


def test_global014_naive_decision_at_rejected_by_global_market_as_of() -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        global_market_as_of({}, datetime(2026, 8, 18, 12, 0))


def test_global014_resolver_returning_naive_datetime_rejected() -> None:
    record = _record(record_id="R1")

    def _naive_resolver(r: GlobalMarketRecord) -> tuple[datetime, AvailabilityBasis]:
        return datetime(2026, 8, 18, 16, 0), AvailabilityBasis.INFERRED

    with pytest.raises(ValueError, match="tz-aware"):
        build_revision_histories([record], resolve_available_at=_naive_resolver)


# --- Common Core Regression: 新規Evidence変換Primitiveを作らず既存を再利用 ---


def test_evidence_reuses_existing_evidence_record_and_source_metadata() -> None:
    record = _record(record_id="R1")
    evidence = global_market_record_to_evidence(
        record,
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        originating_source="PROVIDER",
        delivery_provider="PROVIDER",
    )
    assert evidence.source.originating_source == "PROVIDER"
    # market_public_atへはFallbackしない(retrieved_atが安全な下限として使われる)。
    assert evidence.source.available_at == record.retrieved_at
    assert evidence.layer == DataLayer.NORMALIZED


# --- Defense in depth: series_idにsession_dateを含めない場合の崩壊(Macro D0055と同型) ---


def test_series_id_without_session_date_causes_cross_session_collapse_known_limitation() -> None:
    same_series_id = "SPX_PRICE_INDEX:PROVIDER:DAILY"  # session_dateを含まない(悪い例)
    day1 = _record(record_id="R_DAY1", series_id=same_series_id, session_date=date(2026, 8, 17), value="4990.0")
    day2 = _record(record_id="R_DAY2", series_id=same_series_id, session_date=date(2026, 8, 18), value="5000.12")
    histories = build_revision_histories([day1, day2], resolve_available_at=_us_close_resolver)
    after_day2_close = datetime(2026, 8, 19, 7, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    result = global_market_as_of(histories, after_day2_close)
    assert result[same_series_id] is not None
    assert result[same_series_id].value == "5000.12"  # day1(8/17)の値へは到達できない


def test_series_id_without_index_return_type_causes_cross_type_collapse_known_limitation() -> None:
    """`series_id`が`index_return_type`(Price Index vs Total Return等)を
    含まない場合も、session_dateと同型のCollapseが起こる(skeptic-reviewer
    Finding、Phase4E-1: `model.py`Docstringが挙げる区別軸のうち`session_
    date`以外——`index_return_type`/`price_type`/`currency`——にはPinning
    Testが無かったGap。ここでは`index_return_type`のケースを代表として
    固定する)。"""
    same_series_id = "SPX:PROVIDER:DAILY:2026-08-18"  # index_return_typeを含まない(悪い例)
    price = _record(record_id="R_PRICE", series_id=same_series_id, value="5000.12")
    total_return = GlobalMarketRecord(
        record_id="R_TR",
        series_id=same_series_id,
        instrument_category=InstrumentCategory.EQUITY_INDEX,
        index_return_type=IndexReturnType.TOTAL_RETURN,
        metric_name="SPX_TOTAL_RETURN",
        source_id="PROVIDER",
        frequency=Frequency.DAILY,
        session_date=date(2026, 8, 18),
        market_timezone="America/New_York",
        raw_value="11000.55",
        value=Decimal("11000.55"),
        unit="index points",
        value_availability=ValueAvailability.PRESENT,
        retrieved_at=RETRIEVED_AT_UTC,
        normalizer_version="TEST_V1",
    )
    histories = build_revision_histories([price, total_return], resolve_available_at=_us_close_resolver)
    after_close = datetime(2026, 8, 19, 7, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    result = global_market_as_of(histories, after_close)
    assert result[same_series_id] is not None
    # priceとtotal_returnのavailable_atが同一(同一session_date/market_timezone)のため、
    # RevisionHistory.as_of()のTie-breakはinput順依存(Macro D0055で確認済みのCommon Core
    # 既知挙動)——ここではリスト内で先に渡したpriceが決定論的に勝つ。Total Return(11000.55)
    # へは`global_market_as_of()`経由で二度と到達できなくなる。
    assert result[same_series_id].value == "5000.12"


# --- Defense in depth: as_of()経路とEvidence経路のPIT Gateが乖離しうる(pit-auditor Finding) ---


def test_global_market_as_of_and_evidence_filter_usable_at_can_disagree_known_limitation() -> None:
    """pit-auditor Finding(Phase4E-1、HIGH): `global_market_as_of()`は
    `resolve_available_at`(DST-aware、実際のSession Close)を基準にPIT
    判定するが、`global_market_record_to_evidence()`経由で`lib.evidence.
    retrieval.retrieve_evidence()`/`filter_usable_at()`へ渡した場合の
    PIT判定は`record.retrieved_at`のみを基準にする(D0049/D0050 PIT-003
    原則)。`retrieved_at`が実際のSession Closeより前(例:未確定の
    In-progress SessionをBatch取得した場合)だと、2つの経路が同一Recordに
    ついて異なるUsability判定を返しうる。これはFundamentals/Positioning/
    Macroにも共通するCommon Core既存挙動であり、このRoundが持ち込んだ
    新規Bugではない(DECISIONS.md D0056参照)。Global Market固有のAdapter
    実装が無いためこのRoundでは修正せず、既知の挙動としてPinning Testで
    固定する。"""
    session_close_at = datetime(2026, 8, 18, 16, 0, tzinfo=ZoneInfo("America/New_York"))
    early_retrieved_at = session_close_at - timedelta(hours=2)  # Session Close前に取得(In-progress Batch想定)
    record = _record(record_id="R1", retrieved_at=early_retrieved_at)
    decision_at = session_close_at - timedelta(hours=1)  # まだSession Close前

    histories = build_revision_histories([record], resolve_available_at=_us_close_resolver)
    as_of_result = global_market_as_of(histories, decision_at)
    assert as_of_result[record.series_id] is None  # Session Close前なので正しく利用不可

    evidence = global_market_record_to_evidence(
        record,
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        originating_source="PROVIDER",
        delivery_provider="PROVIDER",
    )
    usable_via_evidence = filter_usable_at([evidence], decision_at)
    # retrieved_at(Session Close前)のみを基準にするEvidence経路は、同じdecision_atで
    # 利用可能と判定してしまう——as_of()経路とは異なる結論になる(乖離の実証)。
    assert len(usable_via_evidence) == 1
