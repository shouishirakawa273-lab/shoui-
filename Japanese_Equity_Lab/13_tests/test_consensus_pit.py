"""`lib.consensus`のPIT Test(Phase4E-4)。Test IDはユーザーTask仕様の
CONS-*に対応する(期待値はPhase4E-4要件から導出、実装からのコピーでは
ない)。

Phase4E-2/4E-3のReviewer Findingを踏まえ、このRoundでは最初から:
- 「Fieldが読まれていないこと」の確認はAST Attribute Accessの走査
  (Docstring内の言及と誤検出しない、単純な文字列探索より厳密)。
- 「Moduleをimportしていないこと」の確認はFully Qualified Pathを
  組み立てるAST走査(`from X import Y`形の検出漏れを防ぐ、Phase4E-3
  GNEWS-016のpit-auditor Finding修正を最初から反映)。
- Cross-source/Cross-statistic比較Testは、実際に何を証明しているか
  (Mechanical Pinning vs 意味論的証明)を過大に説明しない
  (Phase4E-3 skeptic-reviewer Findingを踏まえる)。
を徹底する。
"""

from __future__ import annotations

import ast
from datetime import UTC, date, datetime
from decimal import Decimal

from lib.consensus.evidence import consensus_record_to_evidence
from lib.consensus.model import ConsensusRecord, ForecastHorizon, StatisticType
from lib.consensus.normalize import build_revision_histories
from lib.consensus.view import consensus_as_of
from lib.evidence.model import AvailabilityBasis, ValueAvailability
from lib.fundamentals.model import ConsolidationScope, PeriodType
from lib.sources.catalog import SourceAuthorityClass

RETRIEVED_AT = datetime(2026, 8, 18, 20, 0, tzinfo=UTC)


def _record(
    *,
    record_id: str,
    series_id: str = "S1",
    source_id: str = "TEST_PROVIDER",
    source_entity_identifier: str = "7203",
    entity_id: str | None = None,
    metric_type: str = "EPS",
    statistic_type: StatisticType = StatisticType.MEAN,
    analyst_count: int | None = None,
    target_period_start: date | None = date(2026, 4, 1),
    target_period_end: date | None = date(2027, 3, 31),
    provider_target_period_id: str | None = "FY1",
    forecast_horizon: ForecastHorizon = ForecastHorizon.UNKNOWN,
    period_type: PeriodType = PeriodType.FY,
    fiscal_year_end: date | None = date(2027, 3, 31),
    accounting_scope: ConsolidationScope | None = None,
    raw_value: str | None = "100",
    value: Decimal | None = Decimal("100"),
    value_availability: ValueAvailability = ValueAvailability.PRESENT,
    provider_stated_as_of: datetime | None = None,
    published_at: datetime | None = None,
    published_at_basis: AvailabilityBasis = AvailabilityBasis.UNKNOWN,
    provider_available_at: datetime | None = None,
    provider_available_at_basis: AvailabilityBasis = AvailabilityBasis.UNKNOWN,
    retrieved_at: datetime = RETRIEVED_AT,
) -> ConsensusRecord:
    return ConsensusRecord(
        record_id=record_id,
        series_id=series_id,
        source_id=source_id,
        source_entity_identifier=source_entity_identifier,
        entity_id=entity_id,
        metric_type=metric_type,
        statistic_type=statistic_type,
        analyst_count=analyst_count,
        target_period_start=target_period_start,
        target_period_end=target_period_end,
        provider_target_period_id=provider_target_period_id,
        forecast_horizon=forecast_horizon,
        period_type=period_type,
        fiscal_year_end=fiscal_year_end,
        accounting_scope=accounting_scope,
        raw_value=raw_value,
        value=value,
        value_availability=value_availability,
        provider_stated_as_of=provider_stated_as_of,
        published_at=published_at,
        published_at_basis=published_at_basis,
        provider_available_at=provider_available_at,
        provider_available_at_basis=provider_available_at_basis,
        retrieved_at=retrieved_at,
        normalizer_version="TEST_V1",
    )


def _resolver(record: ConsensusRecord) -> tuple[datetime, AvailabilityBasis]:
    if record.provider_available_at is not None:
        return record.provider_available_at, record.provider_available_at_basis
    return record.retrieved_at, AvailabilityBasis.OBSERVED


def _fields_never_attribute_accessed(module: object, field_names: tuple[str, ...]) -> None:
    """`module`のSource Text全体ではなく、実際のAttribute Access(`x.field`
    形のAST Node)のみを走査する——Docstring内でFieldの存在に言及していても
    誤検出しない(単純な文字列探索より厳密、Phase4E-3 pit-auditor/
    skeptic-reviewer Findingの教訓)。"""
    source = module.__file__  # type: ignore[attr-defined]
    assert source is not None
    text = open(source, encoding="utf-8").read()
    tree = ast.parse(text)
    accessed: set[str] = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    for field_name in field_names:
        assert field_name not in accessed, (module.__name__, field_name)  # type: ignore[attr-defined]


def _source_excluding_docstrings(module: object) -> str:
    """`module`のSource Textから、Module/Class/Function Docstringの中身
    (このLab自身が「〜を生成しない」と説明するために使う語自体を含みうる)
    を除いたTextを返す——Forbidden Term Scanの誤検出("beat"という語が
    「Beat/Missを生成しない」というDocstring自身に含まれる、等)を防ぐ。"""
    source = module.__file__  # type: ignore[attr-defined]
    assert source is not None
    text = open(source, encoding="utf-8").read()
    tree = ast.parse(text)
    docstrings: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                docstrings.append(doc)
    for doc in docstrings:
        text = text.replace(doc, "")
    return text


def _module_never_imports(module: object, forbidden_dotted_path: str) -> None:
    """`from X import Y`形も含めFully Qualified Pathで判定する(Phase4E-3
    GNEWS-016 pit-auditor Findingの修正を最初から反映)。"""
    source = module.__file__  # type: ignore[attr-defined]
    assert source is not None
    text = open(source, encoding="utf-8").read()
    tree = ast.parse(text)
    imported_targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_targets.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_targets.add(node.module)
            imported_targets.update(f"{node.module}.{alias.name}" for alias in node.names)
    assert not any(
        target == forbidden_dotted_path or target.startswith(forbidden_dotted_path + ".") for target in imported_targets
    ), imported_targets


# --- CONS-001: Current Consensus Is Not Historical Consensus ---


def test_cons001_as_of_selects_the_vintage_visible_at_that_time_not_the_latest() -> None:
    early = _record(
        record_id="V1",
        raw_value="100",
        value=Decimal("100"),
        provider_available_at=datetime(2026, 6, 1, tzinfo=UTC),
        provider_available_at_basis=AvailabilityBasis.EXACT,
    )
    late = _record(
        record_id="V2",
        raw_value="105",
        value=Decimal("105"),
        provider_available_at=datetime(2026, 7, 1, tzinfo=UTC),
        provider_available_at_basis=AvailabilityBasis.EXACT,
    )
    histories = build_revision_histories([early, late], resolve_available_at=_resolver)
    mid_decision = datetime(2026, 6, 15, tzinfo=UTC)
    result = consensus_as_of(histories, mid_decision)
    assert result["S1"] is not None
    assert result["S1"].value == "100"  # 2026-07-01時点のVintage(105)はまだ見えない


# --- CONS-002: Future Vintage Leakage ---


def test_cons002_future_vintage_not_visible_to_past_decision_at() -> None:
    future_vintage = _record(
        record_id="V1",
        provider_available_at=datetime(2030, 1, 1, tzinfo=UTC),
        provider_available_at_basis=AvailabilityBasis.EXACT,
    )
    histories = build_revision_histories([future_vintage], resolve_available_at=_resolver)
    result = consensus_as_of(histories, datetime(2026, 8, 18, tzinfo=UTC))
    assert result["S1"] is None


# --- CONS-003: Consensus AsOf != Provider Availability ---


def test_cons003_provider_stated_as_of_never_read_by_normalize_view_or_evidence() -> None:
    import lib.consensus.evidence as evidence_module
    import lib.consensus.normalize as normalize_module
    import lib.consensus.view as view_module

    for module in (normalize_module, view_module, evidence_module):
        _fields_never_attribute_accessed(module, ("provider_stated_as_of",))


def test_cons003_provider_stated_as_of_disagreeing_with_provider_available_at_does_not_affect_availability() -> None:
    record = _record(
        record_id="V1",
        provider_stated_as_of=datetime(2026, 1, 1, tzinfo=UTC),  # Providerの主張する"as of"(Snapshot計算日等、意味不明)
        provider_available_at=datetime(2026, 7, 1, tzinfo=UTC),  # 実際にこのLabが参照可能になった時刻
        provider_available_at_basis=AvailabilityBasis.EXACT,
    )
    histories = build_revision_histories([record], resolve_available_at=_resolver)
    # provider_stated_as_of(2026-01-01)より後だがprovider_available_at(2026-07-01)より前なら見えない
    assert consensus_as_of(histories, datetime(2026, 3, 1, tzinfo=UTC))["S1"] is None
    assert consensus_as_of(histories, datetime(2026, 8, 1, tzinfo=UTC))["S1"] is not None


# --- CONS-004: Unknown Provider Availability Fails Closed ---


def test_cons004_resolver_fallback_to_retrieved_at_is_a_caller_choice_not_a_framework_guarantee() -> None:
    """`_resolver`(このTest File自身のHelper)は`provider_available_at`が
    無い場合`retrieved_at`をOBSERVED Basisとして返す(楽観的Fallback)——
    これは「TimestampがなければFrameworkが自動的にFail Closedする」という
    保証では**ない**(pit-auditor Finding、Phase4E-4: 元のTest名`_excluded_
    by_default`は、実際にはVisibleになるこのTestの結果と矛盾していた)。
    実際のFail Closed保証は`RevisionHistory.as_of()`が`availability_basis
    == UNKNOWN`のVersionを除外する Logic 自体にあり、それは次のTest
    (`test_cons004_unknown_basis_excluded_even_when_timestamp_itself_is_
    present`)が直接検証する——将来Adapterがこの`_resolver`のような楽観的
    Fallbackを安易に実装すると、Timestamp不在のRecordを誤って可視化
    しうることへの警告的Testでもある。"""
    record = _record(record_id="V1")  # provider_available_atなし
    histories = build_revision_histories([record], resolve_available_at=_resolver)
    result = consensus_as_of(histories, datetime(2030, 1, 1, tzinfo=UTC))
    assert result["S1"] is not None  # _resolverが楽観的にretrieved_at/OBSERVEDへFallbackするため


def test_cons004_pessimistic_resolver_reporting_unknown_basis_is_excluded_by_default() -> None:
    """Timestamp自体が無い場合に、Resolverが誠実に`AvailabilityBasis.
    UNKNOWN`(未確認)を返すと(上記の楽観的`_resolver`とは異なる、より
    現実的なCaller実装)、`RevisionHistory.as_of()`のFail Closed Guardが
    実際に機能してExcludeされることを直接確認する(CONS-004の本来の主張
    そのもの)。"""

    def pessimistic_resolver(rec: ConsensusRecord) -> tuple[datetime, AvailabilityBasis]:
        if rec.provider_available_at is not None:
            return rec.provider_available_at, rec.provider_available_at_basis
        return rec.retrieved_at, AvailabilityBasis.UNKNOWN

    record = _record(record_id="V1")  # provider_available_atなし
    histories = build_revision_histories([record], resolve_available_at=pessimistic_resolver)
    result = consensus_as_of(histories, datetime(2030, 1, 1, tzinfo=UTC))
    assert result["S1"] is None


def test_cons004_unknown_basis_excluded_even_when_timestamp_itself_is_present() -> None:
    record = _record(
        record_id="V1",
        provider_available_at=datetime(2026, 1, 1, tzinfo=UTC),
        provider_available_at_basis=AvailabilityBasis.UNKNOWN,
    )
    histories = build_revision_histories(
        [record], resolve_available_at=lambda r: (r.provider_available_at, r.provider_available_at_basis)
    )
    result = consensus_as_of(histories, datetime(2030, 1, 1, tzinfo=UTC))
    assert result["S1"] is None


# --- CONS-005: Date-only AsOf Does Not Guess Time ---


def test_cons005_target_period_is_date_only_and_never_gains_a_time_component() -> None:
    record = _record(record_id="V1", target_period_start=date(2026, 4, 1), target_period_end=date(2027, 3, 31))
    assert type(record.target_period_start) is date
    assert type(record.target_period_end) is date


def test_cons005_provider_stated_as_of_requires_tz_aware_datetime_if_set() -> None:
    import pytest

    with pytest.raises(ValueError, match="tz-aware"):
        _record(record_id="V1", provider_stated_as_of=datetime(2026, 8, 18))  # naive


# --- CONS-006: Forecast Evolution Is Not Correction ---


def test_cons006_forecast_evolution_across_vintages_never_marks_is_correction() -> None:
    v1 = _record(record_id="V1", raw_value="100", provider_available_at=datetime(2026, 6, 1, tzinfo=UTC))
    v2 = _record(record_id="V2", raw_value="105", provider_available_at=datetime(2026, 7, 1, tzinfo=UTC))
    v3 = _record(record_id="V3", raw_value="103", provider_available_at=datetime(2026, 8, 1, tzinfo=UTC))
    histories = build_revision_histories([v1, v2, v3], resolve_available_at=_resolver)
    for version in histories["S1"].versions:
        assert version.is_correction is False
        assert version.supersedes_version_id is None


# --- CONS-007: Missing Estimate Is Not Zero ---


def test_cons007_missing_estimate_stays_none_not_zero() -> None:
    record = _record(record_id="V1", raw_value=None, value=None, value_availability=ValueAvailability.MISSING_OR_UNSPECIFIED)
    assert record.value is None
    assert record.value != Decimal("0")


# --- CONS-008: Mean != Median ---


def test_cons008_mean_and_median_are_distinct_statistic_types() -> None:
    mean_record = _record(record_id="V1", statistic_type=StatisticType.MEAN)
    median_record = _record(record_id="V2", statistic_type=StatisticType.MEDIAN)
    assert mean_record.statistic_type != median_record.statistic_type


# --- CONS-009: Analyst Count Preserved ---


def test_cons009_analyst_count_round_trips_unchanged() -> None:
    few_analysts = _record(record_id="V1", analyst_count=2)
    many_analysts = _record(record_id="V2", analyst_count=30)
    assert few_analysts.analyst_count == 2
    assert many_analysts.analyst_count == 30


# --- CONS-010: Fiscal Period Identity ---


def test_cons010_quarter_and_fy_period_types_are_distinguishable_and_do_not_collapse_if_series_id_reflects_them() -> None:
    quarter = _record(record_id="V1", series_id="ENT7203|EPS|MEAN|Q1|FY2027", period_type=PeriodType.Q1)
    full_year = _record(record_id="V2", series_id="ENT7203|EPS|MEAN|FY|FY2027", period_type=PeriodType.FY)
    histories = build_revision_histories([quarter, full_year], resolve_available_at=_resolver)
    assert set(histories.keys()) == {"ENT7203|EPS|MEAN|Q1|FY2027", "ENT7203|EPS|MEAN|FY|FY2027"}


def test_cons010_period_type_collapse_if_caller_reuses_same_series_id_known_limitation() -> None:
    """`series_id`にperiod_typeを含めない責務違反をCallerが犯した場合、
    Fundamentals/Macro/Global Marketと同じCommon Core Known Limitationが
    再現することをPinする(このDataclass自体は一意性を強制しない)。"""
    quarter = _record(record_id="V1", series_id="SAME_ID", period_type=PeriodType.Q1, raw_value="10")
    full_year = _record(record_id="V2", series_id="SAME_ID", period_type=PeriodType.FY, raw_value="40")
    histories = build_revision_histories([quarter, full_year], resolve_available_at=_resolver)
    assert len(histories["SAME_ID"].versions) == 2  # Collapseせず両方保持されるが、


# --- CONS-011: Current FY != Next FY ---


def test_cons011_current_fy_and_next_fy_are_distinguishable_via_forecast_horizon_and_target_period() -> None:
    current_fy = _record(
        record_id="V1",
        forecast_horizon=ForecastHorizon.CURRENT_FY,
        target_period_start=date(2026, 4, 1),
        target_period_end=date(2027, 3, 31),
    )
    next_fy = _record(
        record_id="V2",
        forecast_horizon=ForecastHorizon.NEXT_FY,
        target_period_start=date(2027, 4, 1),
        target_period_end=date(2028, 3, 31),
    )
    assert current_fy.forecast_horizon != next_fy.forecast_horizon
    assert current_fy.target_period_end != next_fy.target_period_end


# --- CONS-012/013: Company Guidance != Consensus, Actual != Consensus ---


def test_cons012_cons013_consensus_record_has_no_guidance_or_actual_value_field() -> None:
    import dataclasses

    field_names = {f.name for f in dataclasses.fields(ConsensusRecord)}
    forbidden = {"guidance_value", "actual_value", "company_forecast_value", "actual_or_forecast"}
    assert field_names.isdisjoint(forbidden)


# --- CONS-014/015: No Beat/Miss/BUY/SELL Inference ---


def test_cons014_cons015_no_interpretive_or_investment_terms_anywhere_in_lib_consensus() -> None:
    import lib.consensus.evidence as evidence_module
    import lib.consensus.model as model_module
    import lib.consensus.normalize as normalize_module
    import lib.consensus.view as view_module

    forbidden_terms = (
        "beat",
        "miss",
        "surprise",
        "priced_in",
        "priced-in",
        "buy",
        "sell",
        "bullish",
        "bearish",
    )
    for module in (model_module, normalize_module, view_module, evidence_module):
        text = _source_excluding_docstrings(module).lower()
        for term in forbidden_terms:
            assert term not in text, (module.__name__, term)


# --- CONS-016: Historical API Response Is Not Historical Vintage ---
# Adapter未実装のため再現可能なExecution Pathが無く、Code Testではなく
# CONSENSUS_ARCHITECTURE.mdのKnown Limitationとして文書化する
# (NEWS-016/GLOBAL-*と同じ扱い)。


# --- CONS-017: Entity Ambiguity Fails Closed ---


def test_cons017_entity_id_defaults_to_none_and_is_not_auto_filled() -> None:
    record = _record(record_id="V1", entity_id=None, source_entity_identifier="AMBIGUOUS_SYMBOL")
    assert record.entity_id is None


def test_cons017_evidence_related_codes_empty_when_entity_id_unmapped() -> None:
    record = _record(record_id="V1", entity_id=None)
    evidence = consensus_record_to_evidence(
        record,
        source_authority_class=SourceAuthorityClass.VERIFIED_SECONDARY,
        originating_source="TestOrig",
        delivery_provider="TestDelivery",
    )
    assert evidence.related_codes == ()


# --- CONS-018: Unit/Currency Preservation ---


def test_cons018_unit_and_currency_round_trip_unchanged() -> None:
    record = ConsensusRecord(
        record_id="V1",
        series_id="S1",
        source_id="TEST_PROVIDER",
        source_entity_identifier="7203",
        metric_type="EPS",
        statistic_type=StatisticType.MEAN,
        raw_value="105.5",
        value=Decimal("105.5"),
        unit="JPY",
        currency="JPY",
        value_availability=ValueAvailability.PRESENT,
        retrieved_at=RETRIEVED_AT,
        normalizer_version="TEST_V1",
    )
    assert record.unit == "JPY"
    assert record.currency == "JPY"


# --- CONS-019: Determinism ---


def test_cons019_same_input_produces_same_as_of_output() -> None:
    record = _record(
        record_id="V1",
        provider_available_at=datetime(2026, 7, 1, tzinfo=UTC),
        provider_available_at_basis=AvailabilityBasis.EXACT,
    )
    histories = build_revision_histories([record], resolve_available_at=_resolver)
    decision_at = datetime(2026, 8, 18, tzinfo=UTC)
    assert consensus_as_of(histories, decision_at) == consensus_as_of(histories, decision_at)


# --- CONS-020: No Backtest Wiring ---


def test_cons020_evidence_module_never_imports_retrieval_or_filter_usable_at() -> None:
    import lib.consensus.evidence as evidence_module
    import lib.consensus.model as model_module
    import lib.consensus.normalize as normalize_module
    import lib.consensus.view as view_module

    for module in (model_module, normalize_module, view_module, evidence_module):
        _module_never_imports(module, "lib.evidence.retrieval")


# --- CONS-021: Same Metric Different Statistic Does Not Collapse ---


def test_cons021_mean_and_median_use_distinct_series_ids_and_do_not_collapse() -> None:
    mean_record = _record(record_id="V1", series_id="ENT7203|EPS|MEAN|FY2027", statistic_type=StatisticType.MEAN)
    median_record = _record(record_id="V2", series_id="ENT7203|EPS|MEDIAN|FY2027", statistic_type=StatisticType.MEDIAN)
    histories = build_revision_histories([mean_record, median_record], resolve_available_at=_resolver)
    assert set(histories.keys()) == {"ENT7203|EPS|MEAN|FY2027", "ENT7203|EPS|MEDIAN|FY2027"}


# --- CONS-022: Same Metric Different Target Period Does Not Collapse ---


def test_cons022_current_fy_and_next_fy_use_distinct_series_ids_and_do_not_collapse() -> None:
    current = _record(record_id="V1", series_id="ENT7203|EPS|MEAN|FY2027", target_period_end=date(2027, 3, 31))
    next_year = _record(record_id="V2", series_id="ENT7203|EPS|MEAN|FY2028", target_period_end=date(2028, 3, 31))
    histories = build_revision_histories([current, next_year], resolve_available_at=_resolver)
    assert set(histories.keys()) == {"ENT7203|EPS|MEAN|FY2027", "ENT7203|EPS|MEAN|FY2028"}


# --- CONS-023: Same ConsensusAsOf Re-fetch Change Is Not Correction ---


def test_cons023_re_fetch_with_changed_value_at_same_provider_stated_as_of_is_not_marked_correction() -> None:
    same_as_of = datetime(2026, 8, 1, tzinfo=UTC)
    first_fetch = _record(
        record_id="V1",
        raw_value="100",
        provider_stated_as_of=same_as_of,
        provider_available_at=datetime(2026, 8, 1, 9, 0, tzinfo=UTC),
        provider_available_at_basis=AvailabilityBasis.OBSERVED,
        retrieved_at=datetime(2026, 8, 1, 9, 0, tzinfo=UTC),
    )
    re_fetch = _record(
        record_id="V2",
        raw_value="102",  # 同じprovider_stated_as_ofだが値が変わった(Backfill/Aggregation変更等の可能性)
        provider_stated_as_of=same_as_of,
        provider_available_at=datetime(2026, 8, 1, 15, 0, tzinfo=UTC),
        provider_available_at_basis=AvailabilityBasis.OBSERVED,
        retrieved_at=datetime(2026, 8, 1, 15, 0, tzinfo=UTC),
    )
    histories = build_revision_histories([first_fetch, re_fetch], resolve_available_at=_resolver)
    for version in histories["S1"].versions:
        assert version.is_correction is False


# --- CONS-024: Analyst Count Missing Is Not Zero ---


def test_cons024_analyst_count_none_is_not_coerced_to_zero() -> None:
    record = _record(record_id="V1", analyst_count=None)
    assert record.analyst_count is None
    assert record.analyst_count != 0


# --- CONS-025: Relative Horizon Does Not Replace Explicit Target Period ---


def test_cons025_forecast_horizon_never_read_by_normalize_or_view() -> None:
    import lib.consensus.normalize as normalize_module
    import lib.consensus.view as view_module

    for module in (normalize_module, view_module):
        _fields_never_attribute_accessed(module, ("forecast_horizon",))


def test_cons025_explicit_target_period_preserved_independently_of_horizon_label() -> None:
    record = _record(
        record_id="V1",
        forecast_horizon=ForecastHorizon.NEXT_FY,
        target_period_start=date(2027, 4, 1),
        target_period_end=date(2028, 3, 31),
        provider_target_period_id="FY2",
    )
    assert record.target_period_start == date(2027, 4, 1)
    assert record.target_period_end == date(2028, 3, 31)
    assert record.provider_target_period_id == "FY2"


# --- CONS-026: Company Fiscal Year != Calendar Year ---


def test_cons026_fiscal_year_end_and_target_period_end_are_independent_fields() -> None:
    # 2027年3月期(日本の会計年度、fiscal_year_end=2027-03-31)は
    # Calendar 2027(1月-12月)とは異なる期間を指す。
    record = _record(
        record_id="V1",
        target_period_start=date(2026, 4, 1),
        target_period_end=date(2027, 3, 31),
        fiscal_year_end=date(2027, 3, 31),
    )
    assert record.fiscal_year_end == date(2027, 3, 31)
    assert record.fiscal_year_end != date(2027, 12, 31)  # Calendar Year Endと混同していない


def test_cons026_fiscal_year_end_never_derived_from_target_period_end_by_normalize_or_view() -> None:
    import lib.consensus.normalize as normalize_module
    import lib.consensus.view as view_module

    for module in (normalize_module, view_module):
        _fields_never_attribute_accessed(module, ("fiscal_year_end",))


# --- CONS-027: UNKNOWN Accounting Scope Is Not Consolidated ---


def test_cons027_accounting_scope_defaults_to_none_not_consolidated() -> None:
    record = _record(record_id="V1", accounting_scope=None)
    assert record.accounting_scope is None
    assert record.accounting_scope != ConsolidationScope.CONSOLIDATED


# --- CONS-028: Consensus Evidence Is Not Investment Event ---


def test_cons028_evidence_content_has_no_interpretive_or_investment_language() -> None:
    record = _record(record_id="V1")
    evidence = consensus_record_to_evidence(
        record,
        source_authority_class=SourceAuthorityClass.VERIFIED_SECONDARY,
        originating_source="TestOrig",
        delivery_provider="TestDelivery",
    )
    forbidden_terms = ("buy", "sell", "bullish", "bearish", "beat", "miss", "upside", "downside")
    content_lower = evidence.content.lower()
    for term in forbidden_terms:
        assert term not in content_lower, f"Evidence Contentに解釈語 '{term}' が含まれています"


# --- CONS-029: Provider A Mean != Provider B Mean automatically ---


def test_cons029_records_from_different_sources_stay_in_separate_series_when_caller_scopes_series_id_by_source() -> None:
    """`build_revision_histories()`は`series_id`のみでGroupingし、`source_id`
    を暗黙にScopeへ含めない——Provider AとProvider Bの値を同一Seriesへ
    混ぜない責務はCaller(series_id構築側)にある、というMechanical Pinning
    (Fundamentals/Macro/Global Marketと同じ責務分担、Phase4E-3 skeptic-
    reviewer Findingを踏まえ「意味論的に区別した」とは説明しない)。"""
    provider_a = _record(record_id="V1", series_id="PROVIDER_A|ENT7203|EPS|MEAN|FY2027", source_id="PROVIDER_A", raw_value="100")
    provider_b = _record(record_id="V2", series_id="PROVIDER_B|ENT7203|EPS|MEAN|FY2027", source_id="PROVIDER_B", raw_value="110")
    histories = build_revision_histories([provider_a, provider_b], resolve_available_at=_resolver)
    assert histories["PROVIDER_A|ENT7203|EPS|MEAN|FY2027"].versions[0].value == "100"
    assert histories["PROVIDER_B|ENT7203|EPS|MEAN|FY2027"].versions[0].value == "110"


# --- CONS-030: Source-specific Analyst Universe Is Preserved ---


def test_cons030_analyst_count_preserved_independently_per_source_no_averaging() -> None:
    provider_a = _record(record_id="V1", series_id="PROVIDER_A|S", source_id="PROVIDER_A", analyst_count=2)
    provider_b = _record(record_id="V2", series_id="PROVIDER_B|S", source_id="PROVIDER_B", analyst_count=30)
    assert provider_a.analyst_count == 2
    assert provider_b.analyst_count == 30
    # 平均化・統合された単一のanalyst_countへ潰されていない
    assert provider_a.analyst_count != provider_b.analyst_count
