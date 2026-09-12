"""J-Quants `/v2/fins/summary` Raw Payload -> `DisclosureEnvelope`/`FundamentalMetric`。

**確認状況(D0043 + Local Real Data Validation追記)**: このセッション自体は
J-Quants公式ドキュメントへ引き続き疎通できない(DECISIONS.md D0043「A」)。
ただし2026-08-16、ユーザーがローカルPC環境で実際に`/v2/fins/summary`
(7203/6758/8056/3626の4銘柄)へ接続し、実Raw Responseの一部Field名・
Wire Format(値の型)・DocType値を確認した(DECISIONS.md D0043「Local Real
Data Validation Results」参照)。以下はその確認状況を反映している:

- **Local Real Dataで確認済み**: `Sales`/`OP`/`OdP`/`NP`/`EPS`/`BPS`/`NxFSales`/
  `SigChgInC`/`RetroRst`/`MatChgSub`のField名が実在すること、数値も文字列
  (例: `Sales="15481299000000"`、`EPS="109.28"`)として返ること、欠損値は
  空文字列として返ること、boolean的な値も文字列(`MatChgSub="false"`)として
  返ること、`DiscNo`が`DiscDate`から機械的に導出できる値ではないこと(実観測例:
  `DiscNo=20220204580837`だが`DiscDate=2022-02-09`)。DocTypeについて、4銘柄
  すべてで`1Q`/`2Q`/`3Q`/`FY`の各期間で`*FinancialStatements_Consolidated_
  IFRS`(7203/6758/8056)または`*FinancialStatements_Consolidated_JP`
  (3626)のいずれかを確認した。**ただし`_JP`接尾辞が公式に何を意味するか
  (例: JGAAPと同義か)は未確認であり、`"JGAAP"`という名称は採用していない**
  (`ACCOUNTING_STANDARD_PROVIDER_SUFFIX_JP`参照)。
- **依然未検証**: 上記以外のField(`TA`/`Eq`/`EqAR`/`CFO`/`CFI`/`CFF`/`CashEq`/
  Dividend関連/Share Count関連/`ROE`等、Raw Payloadには保持されるがMetricへは
  未マッピング)、Non-Consolidated DocType、USGAAPのDocType、4Q/5Qの実データ、
  Forecast Revision専用DocType、Correction/Restatement Relationship、
  Pagination実挙動、Rate Limit実挙動、`_JP`接尾辞の公式な意味。

**`_METRIC_FIELD_MAP`/`_DOC_TYPE_TO_ACCOUNTING_STANDARD`は上記の確認状況を反映した
ものであり、それでもなお完全な公式仕様確認ではない。** ローカル環境で追加のField
不一致が見つかった場合、コードを無断で書き換えずDECISIONS.md D0043へ追記すること。
**DocType文字列のsubstring heuristicでAccounting Standard/Consolidation Scope/
Disclosure Event Typeを推測することは禁止する。** 未知のDocTypeは
`accounting_standard=None`へfail closedし、warningログを残す(監査可能性)。

Consolidated/Non-Consolidatedの区別は、DocTypeからの推測ではなく、値をどの
Field群(Sales/OP等 vs NCSales/NCOP等)から取得したかという構造的な事実で決める。

**Period/Coverage Semantics(Local Real Data Validationで判明)**: `/v2/fins/
summary`への`code`指定クエリは、Price API(`/v2/equities/bars/daily`)とは異なり、
`from`/`to`で指定した期間に絞り込まれるとは限らない(実観測: `--start 2024-01-01
--end 2024-12-31`を指定しても、対象Codeが持つ取得可能な全履歴(2021-11-04〜
2026-08-04、20件)が返った)。したがってRaw取得の実際のCoverageは
`raw_disclosure_date_range()`で確認すること(Requested Research WindowとRaw
Provider Coverageは別概念、DECISIONS.md D0043参照)。

Rawからの変換方針:

- Empty StringをNoneへ変更しない(`_optional_str`は空文字列をそのまま保持し、
  `None`と空文字列を区別する。値の意味判定=`resolve_value_availability`は
  別途行う)。
- 5桁Provider Codeは書き換えない(`normalize_provider_code_to_internal`で
  内部Codeを別途導出するのみ、`provider_code`は生の値のまま保持する)。
- Numeric StringもBoolean的な文字列も勝手に一括変換しない。数値文字列は
  `Decimal`でParseし精度を保つ(大きな整数値・小数値のいずれも`Decimal`で
  安全に扱える)。Boolean的な文字列は`parse_boolean_string()`で明示的な
  literalのみ受理し、Python truthiness(`bool("false")`は`True`になる)は
  使わない。未知literalは`None`(UNKNOWN)へfail closedする。
- `DiscNo`からDisclosure Date/Timeを推測しない(Local Real Dataで両者が一致
  しないケースを確認済み)。PITは常に`DiscDate`/`DiscTime`をSource of Truth
  とする。
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
# metric_type -> (raw field名, Actual/Forecast, 当期/翌期, 連結/非連結, PeriodBasis)
#
# Stage 3.7(D0081): 各DescriptorがPeriodBasisを明示する(暗黙default禁止)。
# 既存Metric(P&L/EPS/Forecast/Cash Flow)は意味を再設計せず、既存挙動どおり
# 全てCUMULATIVEを明示指定する。新規Stock Metric(TA/ShEq/EqAR)のみ
# POINT_IN_TIME(特定value_date時点のSnapshot、期間累計ではない)。
_METRIC_FIELD_MAP: dict[str, tuple[str, ActualOrForecast, FiscalYearTarget, ConsolidationScope, PeriodBasis]] = {
    "sales": (
        "Sales",
        ActualOrForecast.ACTUAL,
        FiscalYearTarget.CURRENT_FISCAL_YEAR,
        ConsolidationScope.CONSOLIDATED,
        PeriodBasis.CUMULATIVE,
    ),
    "operating_profit": (
        "OP",
        ActualOrForecast.ACTUAL,
        FiscalYearTarget.CURRENT_FISCAL_YEAR,
        ConsolidationScope.CONSOLIDATED,
        PeriodBasis.CUMULATIVE,
    ),
    "net_profit": (
        "NP",
        ActualOrForecast.ACTUAL,
        FiscalYearTarget.CURRENT_FISCAL_YEAR,
        ConsolidationScope.CONSOLIDATED,
        PeriodBasis.CUMULATIVE,
    ),
    "sales_current_year_forecast": (
        "FSales",
        ActualOrForecast.COMPANY_FORECAST,
        FiscalYearTarget.CURRENT_FISCAL_YEAR,
        ConsolidationScope.CONSOLIDATED,
        PeriodBasis.CUMULATIVE,
    ),
    "operating_profit_current_year_forecast": (
        "FOP",
        ActualOrForecast.COMPANY_FORECAST,
        FiscalYearTarget.CURRENT_FISCAL_YEAR,
        ConsolidationScope.CONSOLIDATED,
        PeriodBasis.CUMULATIVE,
    ),
    "net_profit_current_year_forecast": (
        "FNP",
        ActualOrForecast.COMPANY_FORECAST,
        FiscalYearTarget.CURRENT_FISCAL_YEAR,
        ConsolidationScope.CONSOLIDATED,
        PeriodBasis.CUMULATIVE,
    ),
    "sales_next_year_forecast": (
        "NxFSales",
        ActualOrForecast.COMPANY_FORECAST,
        FiscalYearTarget.NEXT_FISCAL_YEAR,
        ConsolidationScope.CONSOLIDATED,
        PeriodBasis.CUMULATIVE,
    ),
    "operating_profit_next_year_forecast": (
        "NxFOP",
        ActualOrForecast.COMPANY_FORECAST,
        FiscalYearTarget.NEXT_FISCAL_YEAR,
        ConsolidationScope.CONSOLIDATED,
        PeriodBasis.CUMULATIVE,
    ),
    "net_profit_next_year_forecast": (
        "NxFNP",
        ActualOrForecast.COMPANY_FORECAST,
        FiscalYearTarget.NEXT_FISCAL_YEAR,
        ConsolidationScope.CONSOLIDATED,
        PeriodBasis.CUMULATIVE,
    ),
    "sales_non_consolidated": (
        "NCSales",
        ActualOrForecast.ACTUAL,
        FiscalYearTarget.CURRENT_FISCAL_YEAR,
        ConsolidationScope.NON_CONSOLIDATED,
        PeriodBasis.CUMULATIVE,
    ),
    "operating_profit_non_consolidated": (
        "NCOP",
        ActualOrForecast.ACTUAL,
        FiscalYearTarget.CURRENT_FISCAL_YEAR,
        ConsolidationScope.NON_CONSOLIDATED,
        PeriodBasis.CUMULATIVE,
    ),
    # "OdP"(経常利益)はLocal Real Data Validationで実在するField名として確認済み
    # (D0043追記、7203実Raw Responseで確認)。IFRS/USGAADでblankになりうることの
    # 確認自体は引き続きユーザー確認済み公式仕様(D0043)による。
    "ordinary_profit": (
        "OdP",
        ActualOrForecast.ACTUAL,
        FiscalYearTarget.CURRENT_FISCAL_YEAR,
        ConsolidationScope.CONSOLIDATED,
        PeriodBasis.CUMULATIVE,
    ),
    "ordinary_profit_current_year_forecast": (
        "FOdP",
        ActualOrForecast.COMPANY_FORECAST,
        FiscalYearTarget.CURRENT_FISCAL_YEAR,
        ConsolidationScope.CONSOLIDATED,
        PeriodBasis.CUMULATIVE,
    ),
    "ordinary_profit_next_year_forecast": (
        "NxFOdP",
        ActualOrForecast.COMPANY_FORECAST,
        FiscalYearTarget.NEXT_FISCAL_YEAR,
        ConsolidationScope.CONSOLIDATED,
        PeriodBasis.CUMULATIVE,
    ),
    # "EPS"はLocal Real Data ValidationでDecimal文字列("109.28"等)として実在する
    # Field名と確認済み(D0043追記)。
    "eps": (
        "EPS",
        ActualOrForecast.ACTUAL,
        FiscalYearTarget.CURRENT_FISCAL_YEAR,
        ConsolidationScope.CONSOLIDATED,
        PeriodBasis.CUMULATIVE,
    ),
    "eps_current_year_forecast": (
        "FEPS",
        ActualOrForecast.COMPANY_FORECAST,
        FiscalYearTarget.CURRENT_FISCAL_YEAR,
        ConsolidationScope.CONSOLIDATED,
        PeriodBasis.CUMULATIVE,
    ),
    "eps_next_year_forecast": (
        "NxFEPS",
        ActualOrForecast.COMPANY_FORECAST,
        FiscalYearTarget.NEXT_FISCAL_YEAR,
        ConsolidationScope.CONSOLIDATED,
        PeriodBasis.CUMULATIVE,
    ),
    # Stage 3.6(D0080): CFO/CFI/CFFはLocal Real Data Validation(7203実
    # Snapshot、全20件のDisclosureで確認)でField名が実在し、Sales/OP等と同じ
    # 累計Flow(CurPerSt=FY開始日、CurPerEn=当該期間終了日)であることを確認済み。
    # 2Q値を2Q単独値として再解釈しない(DerivationやStandalone化は行わない)。
    "cash_flow_from_operations": (
        "CFO",
        ActualOrForecast.ACTUAL,
        FiscalYearTarget.CURRENT_FISCAL_YEAR,
        ConsolidationScope.CONSOLIDATED,
        PeriodBasis.CUMULATIVE,
    ),
    "cash_flow_from_investing": (
        "CFI",
        ActualOrForecast.ACTUAL,
        FiscalYearTarget.CURRENT_FISCAL_YEAR,
        ConsolidationScope.CONSOLIDATED,
        PeriodBasis.CUMULATIVE,
    ),
    "cash_flow_from_financing": (
        "CFF",
        ActualOrForecast.ACTUAL,
        FiscalYearTarget.CURRENT_FISCAL_YEAR,
        ConsolidationScope.CONSOLIDATED,
        PeriodBasis.CUMULATIVE,
    ),
    # Stage 3.7(D0081): TA/ShEq/EqARはLocal Real Data Validation(7203実
    # Snapshot、全20件のDisclosureで確認)でField名が実在するBalance Sheet
    # Snapshot Fact(特定value_date時点、期間累計ではない)。ShEq/EqARの正式
    # Provider長名称は未確認のため、metric_typeで意味を過剰確定しない
    # (`shareholders_equity`等の確定的な名称は使わない、"Eq"という別Fieldも
    # Raw Payloadに実在し、値がShEqと異なるため統合しない)。EqARはRaw
    # Provider値をそのまま使い、ShEq/TAからLab側で再計算しない(Validation
    # Testでの整合確認のみ許容、Provider値は上書きしない)。
    "total_assets": (
        "TA",
        ActualOrForecast.ACTUAL,
        FiscalYearTarget.CURRENT_FISCAL_YEAR,
        ConsolidationScope.CONSOLIDATED,
        PeriodBasis.POINT_IN_TIME,
    ),
    "provider_reported_sheq": (
        "ShEq",
        ActualOrForecast.ACTUAL,
        FiscalYearTarget.CURRENT_FISCAL_YEAR,
        ConsolidationScope.CONSOLIDATED,
        PeriodBasis.POINT_IN_TIME,
    ),
    "provider_reported_eqar": (
        "EqAR",
        ActualOrForecast.ACTUAL,
        FiscalYearTarget.CURRENT_FISCAL_YEAR,
        ConsolidationScope.CONSOLIDATED,
        PeriodBasis.POINT_IN_TIME,
    ),
}

# Providerが使う会計基準を表すLabel文字列。IFRSは公式仕様(IFRS/USGAAPには
# 経常利益相当概念が無い)から意味が確認済みの値。一方"_JP"接尾辞DocType
# (下記)は、4銘柄Local Real Data Validation(2026-08-16、7203/6758/8056/
# 3626)でDocType文字列としての実在は確認できたが、この接尾辞が公式仕様上
# 正式に何を意味するか(例: 日本基準=JGAAPと同義か)はJ-Quants公式ドキュメント
# へ疎通できないため確認できていない(DECISIONS.md D0043参照)。したがって
# "JGAAP"という名称を推測で採用せず、"IFRSとは別の会計基準カテゴリである"と
# いう構造的な事実のみを表す`PROVIDER_SUFFIX_JP`という中立的な識別子を使う。
# 公式仕様で正式名称が確認できた時点でMapping先を変更すること(値の意味は
# 変わらない、ラベルのみ変更)。
ACCOUNTING_STANDARD_IFRS = "IFRS"
ACCOUNTING_STANDARD_PROVIDER_SUFFIX_JP = "PROVIDER_SUFFIX_JP"

# DocType文字列 -> Accounting Standard の明示的Mapping(substring heuristic禁止)。
# IFRS 4件・"_JP"接尾辞4件は4銘柄Local Real Data Validationで実在する
# DocType値として確認済み(D0043追記)。それ以外(Non-Consolidated DocType・
# USGAAPのDocType・Forecast Revision専用DocType等)は未確認のため、既定で
# fail closed(None)する。
_DOC_TYPE_TO_ACCOUNTING_STANDARD: dict[str, str] = {
    "1QFinancialStatements_Consolidated_IFRS": ACCOUNTING_STANDARD_IFRS,
    "2QFinancialStatements_Consolidated_IFRS": ACCOUNTING_STANDARD_IFRS,
    "3QFinancialStatements_Consolidated_IFRS": ACCOUNTING_STANDARD_IFRS,
    "FYFinancialStatements_Consolidated_IFRS": ACCOUNTING_STANDARD_IFRS,
    "1QFinancialStatements_Consolidated_JP": ACCOUNTING_STANDARD_PROVIDER_SUFFIX_JP,
    "2QFinancialStatements_Consolidated_JP": ACCOUNTING_STANDARD_PROVIDER_SUFFIX_JP,
    "3QFinancialStatements_Consolidated_JP": ACCOUNTING_STANDARD_PROVIDER_SUFFIX_JP,
    "FYFinancialStatements_Consolidated_JP": ACCOUNTING_STANDARD_PROVIDER_SUFFIX_JP,
}

# 会計基準上、そもそも存在しない指標(ユーザー確認済み公式仕様、D0043)。
# `PROVIDER_SUFFIX_JP`はここに含めない: 経常利益(ordinary_profit)が
# "_JP"接尾辞の会計基準で存在しない、という事実は確認できていないため
# (未確認事項を推測で埋めない、D0043)。
_NOT_APPLICABLE_UNDER_STANDARD: dict[str, frozenset[str]] = {
    ACCOUNTING_STANDARD_IFRS: frozenset({"ordinary_profit"}),
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

# Wire上ではboolean的な値も文字列で返る(Local Real Data Validationで
# `MatChgSub="false"`を確認済み、D0043追記)。許可されたliteralのみ受理する。
_KNOWN_BOOLEAN_LITERALS: dict[str, bool] = {"true": True, "false": False}


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
    """大きな整数値("15481299000000")・小数値("109.28")のいずれも`Decimal`で
    安全にParseする(精度を保つため`float`は使わない、Local Real Data
    Validationで両パターンとも文字列として返ることを確認済み、D0043追記)。"""
    try:
        return Decimal(raw_value)
    except (InvalidOperation, ValueError):
        return None


def parse_boolean_string(raw: str | None) -> bool | None:
    """Wire上のboolean的な値("true"/"false"、Local Real Data Validationで
    `MatChgSub="false"`を確認済み、D0043追記)を厳格にParseする。

    Python truthiness(`bool("false")`は`True`になってしまう)は使わず、
    許可されたliteralのみ受理する。`None`・空文字列・未知literalはいずれも
    `None`(UNKNOWN)へfail closedし、値を推測で確定させない。
    """
    if raw is None:
        return None
    return _KNOWN_BOOLEAN_LITERALS.get(raw)


def _parse_date_or_none(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def raw_disclosure_date_range(payload: Sequence[Mapping[str, object]]) -> tuple[date | None, date | None]:
    """Raw Payload全体の`DiscDate`最小値・最大値を返す(Requested Research
    WindowとRaw Provider Coverageを区別して表示するための補助関数、D0043追記)。

    `/v2/fins/summary`は`code`指定クエリの場合、`from`/`to`で絞り込まれるとは
    限らない(Local Real Data Validationで確認済み)。この関数はRaw Payload
    そのものから実際のCoverageを機械的に求めるのみで、Research Windowによる
    絞り込みは一切行わない。DiscDateが無い/不正な行は無視する。1件も解釈
    できなければ`(None, None)`。
    """
    dates = [d for row in payload if (d := _parse_date_or_none(_optional_str(row.get("DiscDate")))) is not None]
    if not dates:
        return None, None
    return min(dates), max(dates)


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
    Provider Update Policyの「頃」表現をExact Timestampへ変換しない。

    **Docstring修正(D0049追記)**: `anchor`が`market_public_at`(存在する場合)を
    優先する設計は、旧`lib.fundamentals.evidence`の`available_at`Fallback Bug
    (D0049で修正)と同じ「market_public_atは保守的」という逆の論理に基づいて
    いた — `market_public_at`は通常`provider_available_at`より**早く**、これを
    `available_at`相当のFieldへ入れると実際より早く使えたと誤認しうる。ここでは
    `availability_basis`を常に`AvailabilityBasis.UNKNOWN`とすることで、
    `RevisionHistory.as_of()`が既定でこの値を除外し(D0040)、上記の誤認が
    実際にReproducible System Simulationへ漏れることを防いでいる — **安全性は
    `anchor`の値そのものが正しいからではなく、UNKNOWN Basisによる既定除外から
    来ている**(旧Docstringの「market_public_atは保守的」という説明は誤り)。

    呼び出し側が`include_unknown_availability=True`を明示した場合、この
    `anchor`(`market_public_at`優先)がそのまま`available_at`として使われる
    ため、`lib.fundamentals.evidence`で修正したのと同型のLeakageが再現しうる
    (pit-auditor Finding、D0049 §5-1、Follow-up)。この`anchor`計算自体を
    `retrieved_at`固定へ変更するかどうかは、`include_unknown_availability=True`
    の既存呼び出し箇所への影響分析を要する設計判断であり、このDocstring修正
    Roundでは変更しない(挙動不変、Docstringのみ修正)。
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

        # CurPerSt/CurPerEn/CurFYSt/CurFYEn/NxtFYSt/NxtFYEnはLocal Real Data
        # Validationで実在するField名として確認済み(D0043追記)。不正/欠損の場合は
        # 推測補完せずNoneのまま(_parse_date_or_noneがfail closedする)。
        current_period_start = _parse_date_or_none(_optional_str(row.get("CurPerSt")))
        current_period_end = _parse_date_or_none(_optional_str(row.get("CurPerEn")))
        current_fiscal_year_start = _parse_date_or_none(_optional_str(row.get("CurFYSt")))
        current_fiscal_year_end = _parse_date_or_none(_optional_str(row.get("CurFYEn")))
        next_fiscal_year_start = _parse_date_or_none(_optional_str(row.get("NxtFYSt")))
        next_fiscal_year_end = _parse_date_or_none(_optional_str(row.get("NxtFYEn")))

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
            current_period_start=current_period_start,
            current_period_end=current_period_end,
            current_fiscal_year_start=current_fiscal_year_start,
            current_fiscal_year_end=current_fiscal_year_end,
            next_fiscal_year_start=next_fiscal_year_start,
            next_fiscal_year_end=next_fiscal_year_end,
            accounting_standard=accounting_standard,
            source_snapshot_id=source_snapshot_id,
        )
        envelopes.append(envelope)

        for metric_type, (
            source_field,
            actual_or_forecast,
            fiscal_year_target,
            scope,
            period_basis,
        ) in _METRIC_FIELD_MAP.items():
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
                    period_basis=period_basis,
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
    "ACCOUNTING_STANDARD_IFRS",
    "ACCOUNTING_STANDARD_PROVIDER_SUFFIX_JP",
    "NORMALIZER_VERSION",
    "build_revision_histories",
    "parse_boolean_string",
    "parse_financial_summary_payload",
    "raw_disclosure_date_range",
    "resolve_value_availability",
]
