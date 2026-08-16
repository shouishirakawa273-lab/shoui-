"""J-Quants `/v2/fins/summary` Raw Payload -> `DisclosureEnvelope`/`FundamentalMetric`。

**Field名は全て未検証**(このセッションはJ-Quants公式ドキュメントへ疎通できない、
DECISIONS.md D0043参照)。以下の`_METRIC_FIELD_MAP`/`_DOC_TYPE_TO_ACCOUNTING_STANDARD`は
ユーザーがセッション内で提示した情報に基づく作業仮説であり、`_DOC_TYPE_TO_
ACCOUNTING_STANDARD`のエントリはFixture Testで会計基準分岐ロジックを検証するための
仮定義に過ぎない(実際のDocType文字列ではない)。ローカル環境で実レスポンスを
確認した上で必ず修正すること。**DocType文字列のsubstring heuristicで
Accounting Standard/Consolidation Scope/Disclosure Event Typeを推測することは
禁止する。** 未知のDocTypeは`accounting_standard=None`へfail closedし、warning
ログを残す(監査可能性)。

Consolidated/Non-Consolidatedの区別は、DocTypeからの推測ではなく、値をどの
Field群(Sales/OP等 vs NCSales/NCOP等)から取得したかという構造的な事実で決める。

Rawからの変換方針:

- Empty StringをNoneへ変更しない(`_optional_str`は空文字列をそのまま保持し、
  `None`と空文字列を区別する。値の意味判定=`resolve_value_availability`は
  別途行う)。
- 5桁Provider Codeは書き換えない(`normalize_provider_code_to_internal`で
  内部Codeを別途導出するのみ、`provider_code`は生の値のまま保持する)。
- Numeric Stringを勝手にFloatへ変換しない(`Decimal`でParseし、精度を保つ)。
- Provider Rawに含まれる未知のFieldは無視するだけで、Raw自体を破棄・拒否しない
  (Provider Schema Evolutionへの前方互換性、`normalizer_version`で追跡する)。
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from lib.data_sources.ticker_codes import TickerCodeNormalizationError, normalize_provider_code_to_internal
from lib.evidence.model import AvailabilityBasis, RevisionHistory, SourceVersion, ValueAvailability
from lib.fundamentals.model import (
    NORMALIZER_VERSION,
    ActualOrForecast,
    ConsolidationScope,
    DisclosureEnvelope,
    FiscalYearTarget,
    FundamentalMetric,
    PeriodBasis,
    PeriodType,
)
from lib.sources.entity_registry import EntityRegistry

logger = logging.getLogger(__name__)

_JST = ZoneInfo("Asia/Tokyo")

# --- Field Mapping(未検証、DECISIONS.md D0043参照) ---
# metric_type -> (raw field名, Actual/Forecast, 当期/翌期, 連結/非連結)
_METRIC_FIELD_MAP: dict[str, tuple[str, ActualOrForecast, FiscalYearTarget, ConsolidationScope]] = {
    "sales": ("Sales", ActualOrForecast.ACTUAL, FiscalYearTarget.CURRENT_FISCAL_YEAR, ConsolidationScope.CONSOLIDATED),
    "operating_profit": ("OP", ActualOrForecast.ACTUAL, FiscalYearTarget.CURRENT_FISCAL_YEAR, ConsolidationScope.CONSOLIDATED),
    "net_profit": ("NP", ActualOrForecast.ACTUAL, FiscalYearTarget.CURRENT_FISCAL_YEAR, ConsolidationScope.CONSOLIDATED),
    "sales_current_year_forecast": (
        "FSales",
        ActualOrForecast.COMPANY_FORECAST,
        FiscalYearTarget.CURRENT_FISCAL_YEAR,
        ConsolidationScope.CONSOLIDATED,
    ),
    "operating_profit_current_year_forecast": (
        "FOP",
        ActualOrForecast.COMPANY_FORECAST,
        FiscalYearTarget.CURRENT_FISCAL_YEAR,
        ConsolidationScope.CONSOLIDATED,
    ),
    "net_profit_current_year_forecast": (
        "FNP",
        ActualOrForecast.COMPANY_FORECAST,
        FiscalYearTarget.CURRENT_FISCAL_YEAR,
        ConsolidationScope.CONSOLIDATED,
    ),
    "sales_next_year_forecast": (
        "NxFSales",
        ActualOrForecast.COMPANY_FORECAST,
        FiscalYearTarget.NEXT_FISCAL_YEAR,
        ConsolidationScope.CONSOLIDATED,
    ),
    "operating_profit_next_year_forecast": (
        "NxFOP",
        ActualOrForecast.COMPANY_FORECAST,
        FiscalYearTarget.NEXT_FISCAL_YEAR,
        ConsolidationScope.CONSOLIDATED,
    ),
    "net_profit_next_year_forecast": (
        "NxFNP",
        ActualOrForecast.COMPANY_FORECAST,
        FiscalYearTarget.NEXT_FISCAL_YEAR,
        ConsolidationScope.CONSOLIDATED,
    ),
    "sales_non_consolidated": (
        "NCSales",
        ActualOrForecast.ACTUAL,
        FiscalYearTarget.CURRENT_FISCAL_YEAR,
        ConsolidationScope.NON_CONSOLIDATED,
    ),
    "operating_profit_non_consolidated": (
        "NCOP",
        ActualOrForecast.ACTUAL,
        FiscalYearTarget.CURRENT_FISCAL_YEAR,
        ConsolidationScope.NON_CONSOLIDATED,
    ),
    # "ordinary_profit"(経常利益)の生Field名はユーザー未提示・未確認。IFRS/USGAAPで
    # blankになりうることの確認(D0043)をFixture Testで検証するための仮Field名。
    "ordinary_profit": (
        "OrdinaryProfit",
        ActualOrForecast.ACTUAL,
        FiscalYearTarget.CURRENT_FISCAL_YEAR,
        ConsolidationScope.CONSOLIDATED,
    ),
}

# DocType文字列 -> Accounting Standard の明示的Mapping(substring heuristic禁止)。
# 実際のJ-Quants DocType一覧は未確認のため空(既定でfail closed=None)。
# 以下はFixture Test専用の仮エントリであり、実データでの動作を保証しない。
_DOC_TYPE_TO_ACCOUNTING_STANDARD: dict[str, str] = {
    "FYFinancialStatements_Consolidated_IFRS_SYNTH": "IFRS",  # 未確認(Fixture Test用)
}

# 会計基準上、そもそも存在しない指標(ユーザー確認済み公式仕様、D0043)。
_NOT_APPLICABLE_UNDER_STANDARD: dict[str, frozenset[str]] = {
    "IFRS": frozenset({"ordinary_profit"}),
    "USGAAP": frozenset({"ordinary_profit"}),
}

_KNOWN_PERIOD_TYPES: dict[str, PeriodType] = {
    "1Q": PeriodType.Q1,
    "2Q": PeriodType.Q2,
    "3Q": PeriodType.Q3,
    "4Q": PeriodType.Q4,
    "5Q": PeriodType.Q5,
    "FY": PeriodType.FY,
}


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _parse_period_type(raw: object) -> PeriodType:
    """未知のCurPerType値は例外にせず`OTHER`へfail closedし、warningを残す
    (Provider Schema Change検出、D0043)。"""
    if raw is None:
        return PeriodType.OTHER
    raw_str = str(raw)
    period = _KNOWN_PERIOD_TYPES.get(raw_str)
    if period is None:
        logger.warning("fins_summary: 未知のCurPerType値 '%s' を検出しました(Provider Schema Changeの可能性)", raw_str)
        return PeriodType.OTHER
    return period


def _parse_decimal(raw_value: str) -> Decimal | None:
    try:
        return Decimal(raw_value)
    except (InvalidOperation, ValueError):
        return None


def resolve_value_availability(raw_value: str | None, *, accounting_standard: str | None, metric_type: str) -> ValueAvailability:
    """Rawの空文字列だけを見てNOT_APPLICABLEと断定しない。会計基準から明示的に
    確認できる場合のみNOT_APPLICABLEとし、それ以外の空値はMISSING_OR_UNSPECIFIED
    とする(D0043)。"""
    if raw_value is not None and raw_value != "":
        return ValueAvailability.PRESENT
    if accounting_standard is not None and metric_type in _NOT_APPLICABLE_UNDER_STANDARD.get(accounting_standard, frozenset()):
        return ValueAvailability.NOT_APPLICABLE
    return ValueAvailability.MISSING_OR_UNSPECIFIED


def _build_market_public_at(disc_date_raw: str | None, disc_time_raw: str | None) -> tuple[datetime | None, AvailabilityBasis]:
    """DiscDate+DiscTimeからmarket_public_atを構築する。DiscTimeが無い/不明な場合、
    15:00や15:30等を推測で補完しない(D0043)。"""
    if not disc_date_raw or not disc_time_raw:
        return None, AvailabilityBasis.UNKNOWN
    try:
        d = date.fromisoformat(disc_date_raw)
        time_parts = disc_time_raw.split(":")
        hour, minute = int(time_parts[0]), int(time_parts[1])
        dt = datetime(d.year, d.month, d.day, hour, minute, tzinfo=_JST)
    except (ValueError, IndexError):
        return None, AvailabilityBasis.UNKNOWN
    return dt, AvailabilityBasis.EXACT


def _provider_available_at_and_basis(
    market_public_at: datetime | None, retrieved_at: datetime
) -> tuple[datetime, AvailabilityBasis]:
    """provider_available_at(このProvider経由でいつ参照可能になったか)は、実際に
    観測したPolling Log等が無い限り確定できない(D0043)。「18:00頃速報」等の
    Provider Update Policyの「頃」表現をExact Timestampへ変換しない。ここでは
    構造上必須のavailable_at Fieldへ最も保守的なAnchor(market_public_at、無ければ
    retrieved_at)を入れつつ、常に`availability_basis=UNKNOWN`とする。
    `RevisionHistory.as_of()`は既定でUNKNOWN Basisを除外するため、この値が
    Reproducible System Simulationへ「確認済みの事実」として誤って使われることはない。
    """
    anchor = market_public_at if market_public_at is not None else retrieved_at
    return anchor, AvailabilityBasis.UNKNOWN


def parse_financial_summary_payload(
    payload: Sequence[Mapping[str, object]],
    *,
    retrieved_at: datetime,
    source_snapshot_id: str | None = None,
    entity_registry: EntityRegistry | None = None,
) -> tuple[list[DisclosureEnvelope], list[FundamentalMetric]]:
    """`/v2/fins/summary`のRaw Payloadを`DisclosureEnvelope`/`FundamentalMetric`へ
    変換する。正規化に失敗したProvider Code(普通株以外の可能性)はログ警告を出して
    スキップする(`equities_master_payload_to_listing_records`と同じ非厳格な扱い、
    D0036)。"""
    envelopes: list[DisclosureEnvelope] = []
    metrics: list[FundamentalMetric] = []

    for index, row in enumerate(payload):
        provider_code = _optional_str(row.get("Code"))
        if provider_code is None:
            logger.warning("fins_summary: Codeフィールドが無い行をスキップします")
            continue
        try:
            internal_code = normalize_provider_code_to_internal(provider_code)
        except TickerCodeNormalizationError:
            logger.warning(
                "fins_summary: provider_code=%s を内部Codeへ正規化できないためスキップします(普通株以外の可能性)",
                provider_code,
            )
            continue

        disc_no = _optional_str(row.get("DiscNo"))
        doc_type = _optional_str(row.get("DocType"))
        disc_date_raw = _optional_str(row.get("DiscDate"))
        disc_time_raw = _optional_str(row.get("DiscTime"))
        disc_date = date.fromisoformat(disc_date_raw) if disc_date_raw else None
        market_public_at, market_public_at_basis = _build_market_public_at(disc_date_raw, disc_time_raw)
        cur_per_type = _parse_period_type(row.get("CurPerType"))

        accounting_standard = None
        if doc_type is not None:
            accounting_standard = _DOC_TYPE_TO_ACCOUNTING_STANDARD.get(doc_type)
            if accounting_standard is None:
                logger.warning(
                    "fins_summary: 未知のDocType '%s' のためaccounting_standardをUNKNOWN(None)にfail closedします", doc_type
                )

        canonical_entity_id: str | None = None
        if entity_registry is not None and disc_date is not None:
            mapping = entity_registry.resolve(provider_name="jquants", provider_identifier=provider_code, as_of=disc_date)
            canonical_entity_id = mapping.issuer_id if mapping is not None else None

        envelope_id = f"ENV_{internal_code}_{disc_no or index}"
        envelope = DisclosureEnvelope(
            envelope_id=envelope_id,
            provider_code=provider_code,
            internal_code=internal_code,
            canonical_entity_id=canonical_entity_id,
            disclosure_number=disc_no,
            document_type=doc_type,
            disclosure_date=disc_date,
            disclosure_time=disc_time_raw,
            market_public_at=market_public_at,
            market_public_at_basis=market_public_at_basis,
            retrieved_at=retrieved_at,
            current_period_type=cur_per_type,
            accounting_standard=accounting_standard,
            source_snapshot_id=source_snapshot_id,
        )
        envelopes.append(envelope)

        for metric_type, (source_field, actual_or_forecast, fiscal_year_target, scope) in _METRIC_FIELD_MAP.items():
            raw_value = _optional_str(row.get(source_field))
            availability = resolve_value_availability(raw_value, accounting_standard=accounting_standard, metric_type=metric_type)
            value: Decimal | None = None
            if availability == ValueAvailability.PRESENT and raw_value is not None:
                value = _parse_decimal(raw_value)
                if value is None:
                    availability = ValueAvailability.UNKNOWN

            series_id = "|".join(
                [
                    internal_code,
                    metric_type,
                    fiscal_year_target.value,
                    cur_per_type.value,
                    scope.value,
                    accounting_standard or "UNKNOWN",
                ]
            )
            metrics.append(
                FundamentalMetric(
                    metric_id=f"{envelope_id}_{metric_type}",
                    envelope_id=envelope_id,
                    series_id=series_id,
                    metric_type=metric_type,
                    raw_value=raw_value,
                    value=value,
                    value_availability=availability,
                    actual_or_forecast=actual_or_forecast,
                    fiscal_year_target=fiscal_year_target,
                    period_type=cur_per_type,
                    period_basis=PeriodBasis.CUMULATIVE,
                    consolidation_scope=scope,
                    accounting_standard=accounting_standard,
                    source_field=source_field,
                    source_disclosure_number=disc_no,
                )
            )

    return envelopes, metrics


def build_revision_histories(
    envelopes: Sequence[DisclosureEnvelope], metrics: Sequence[FundamentalMetric]
) -> dict[str, RevisionHistory]:
    """`FundamentalMetric`群をseries_idごとにグルーピングし、`RevisionHistory`
    (`lib.evidence.model`、D0040で新設・D0042でrevision_reason追加)を構築する。

    同一entity・同一metric・同一fiscal_year_target・同一period・同一scope・同一
    accounting_standardの複数Disclosureをそのまま時系列で保持する
    (公式仕様でRevision Relationshipが確定できないため、`supersedes_version_id`は
    常に`None`のまま=「関係不明」として扱う。D0043)。`RevisionHistory.as_of()`が
    availability_basis/available_at基準で「その時点で使えた最新のVersion」を
    正しく選ぶため、明示的なsupersedes chainが無くても安全に機能する。
    """
    envelopes_by_id = {e.envelope_id: e for e in envelopes}
    versions_by_series: dict[str, list[SourceVersion]] = {}
    for metric in metrics:
        envelope = envelopes_by_id[metric.envelope_id]
        available_at, availability_basis = _provider_available_at_and_basis(envelope.market_public_at, envelope.retrieved_at)
        version = SourceVersion(
            source_record_id=metric.series_id,
            source_version_id=metric.metric_id,
            value=metric.raw_value if metric.raw_value is not None else "",
            available_at=available_at,
            retrieved_at=envelope.retrieved_at,
            availability_basis=availability_basis,
            is_correction=False,  # Forecast RevisionとCorrection/Restatementを混同しない(D0043、下記Docstring参照)。
            event_at=envelope.current_period_end or envelope.disclosure_date,
            published_at=envelope.market_public_at,
        )
        versions_by_series.setdefault(metric.series_id, []).append(version)
    return {
        series_id: RevisionHistory(series_id=series_id, versions=tuple(versions))
        for series_id, versions in versions_by_series.items()
    }


__all__ = [
    "NORMALIZER_VERSION",
    "build_revision_histories",
    "parse_financial_summary_payload",
    "resolve_value_availability",
]
