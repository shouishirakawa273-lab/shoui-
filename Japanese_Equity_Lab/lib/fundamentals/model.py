"""Fundamental Record Schema(Phase4A、D0043): J-Quants `/v2/fins/summary`由来の
Disclosure(開示)とMetric(指標)を、意味を保持したまま表現する。

**重要な既知の制約**: このセッションはネットワークポリシーにより、J-Quants公式
ドキュメント(`/v2/fins/summary`の正式仕様)へ一切疎通できない(接続試行はDECISIONS.md
D0043に記録済み)。したがって、以下のField名・値の対応関係はユーザーがセッション内で
明示した情報に基づく作業仮説であり、公式仕様で検証したものではない
(`lib/fundamentals/normalize.py`の`_METRIC_FIELD_MAP`/`_DOC_TYPE_TO_ACCOUNTING_STANDARD`
参照)。本番投入前に必ずローカル環境で実レスポンスを確認し、食い違いがあれば
修正すること。

## Disclosure単位で保存する(Wide Tableへ早期に潰さない)

Financial Summaryを``code/date/sales/profit``のような単純なWide Tableへ変換せず、
まず`DisclosureEnvelope`(開示そのもの)と`FundamentalMetric`(指標1件)を分離して
保持する。

## Actual/Forecast/Period/Scopeを混同しない

- `ActualOrForecast`: ACTUAL(実績) / COMPANY_FORECAST(会社予想)。
- `FiscalYearTarget`: CURRENT_FISCAL_YEAR(当期) / NEXT_FISCAL_YEAR(翌期)。
- `PeriodType`: 1Q/2Q/3Q/4Q/5Q/FY(公式仕様上CurPerTypeが取りうる値、未知値は`OTHER`
  として安全側に倒し、即例外で全処理停止しない。Provider Schema Change検出用)。
- `PeriodBasis`: CUMULATIVE(累計) / STANDALONE(単独)。Phase4Aでは常にCUMULATIVEを
  使う(Providerの値をそのまま保持するのみで、2Q累計からQ2単独値を計算する導出は
  Phase4Aでは行わない。将来行う場合は`DataLayer.DERIVED`として明示する)。
- `ConsolidationScope`: CONSOLIDATED(連結) / NON_CONSOLIDATED(非連結)。DocTypeからの
  推測ではなく、どのField群(例: Sales/OP vs NCSales/NCOP)から得た値かという
  構造的な区別で決定する。

## Value Availability(Stored Value State)

`lib.evidence.model.ValueAvailability`(PRESENT/NOT_APPLICABLE/
MISSING_OR_UNSPECIFIED/UNKNOWN)を使う。**As-of時点のTemporal Usability
(問い合わせ時点でまだ利用できないという結果)とは別概念であり混同しない**
(後者は`lib.fundamentals.view.fundamentals_as_of()`が`None`を返すことで表現する)。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from lib.evidence.model import AvailabilityBasis, ValueAvailability

NORMALIZER_VERSION = "FINS_SUMMARY_NORMALIZER_V1"


class PeriodType(StrEnum):
    """CurPerType(公式仕様上、値は1Q/2Q/3Q/4Q/5Q/FY)。未知値は`OTHER`とし、
    即例外で全処理停止せず、Provider Schema Changeとして検出・監査可能にする。"""

    Q1 = "1Q"
    Q2 = "2Q"
    Q3 = "3Q"
    Q4 = "4Q"
    Q5 = "5Q"
    FY = "FY"
    OTHER = "OTHER"


class PeriodBasis(StrEnum):
    """CUMULATIVE: FY開始等から期間末までの累計Flow。STANDALONE: 単独期間Flow
    (Phase4Aでは自動導出しない、CUMULATIVEからの機械的な差分計算は行わない)。
    POINT_IN_TIME(Stage 3.7、D0081): 特定`value_date`時点のSnapshot(Balance
    Sheet Fact等)。累計・単独いずれのFlow概念でもない——`current_period_start`
    を値の期間開始として扱わない(`lib.fundamentals.evidence`参照)。"""

    CUMULATIVE = "CUMULATIVE"
    STANDALONE = "STANDALONE"
    POINT_IN_TIME = "POINT_IN_TIME"


class ConsolidationScope(StrEnum):
    CONSOLIDATED = "CONSOLIDATED"
    NON_CONSOLIDATED = "NON_CONSOLIDATED"


class ActualOrForecast(StrEnum):
    ACTUAL = "ACTUAL"
    COMPANY_FORECAST = "COMPANY_FORECAST"


class FiscalYearTarget(StrEnum):
    CURRENT_FISCAL_YEAR = "CURRENT_FISCAL_YEAR"
    NEXT_FISCAL_YEAR = "NEXT_FISCAL_YEAR"


@dataclass(kw_only=True, frozen=True)
class DisclosureEnvelope:
    """Financial Summary 1件のDisclosure(開示)そのもの。Metricへ潰す前の単位。

    `market_public_at`はDiscDate+DiscTimeから構築する。DiscTimeが無い/不明な場合、
    15:00や15:30等を推測で補完せず`None`のまま(`market_public_at_basis=UNKNOWN`)とする。

    `provider_available_at`(このProvider経由でいつ参照可能になったか)はこの
    Envelope自体には持たない。実際にPIT判定へ使うのは`FundamentalMetric`から
    構築する`SourceVersion.available_at`/`availability_basis`であり
    (`lib.fundamentals.normalize`参照)、両者を混同しない。
    """

    envelope_id: str
    provider_code: str
    internal_code: str
    canonical_entity_id: str | None = None
    disclosure_number: str | None = None
    document_type: str | None = None
    disclosure_date: date | None = None
    disclosure_time: str | None = None
    market_public_at: datetime | None = None
    market_public_at_basis: AvailabilityBasis = AvailabilityBasis.UNKNOWN
    retrieved_at: datetime
    current_period_type: PeriodType = PeriodType.OTHER
    current_period_start: date | None = None
    current_period_end: date | None = None
    current_fiscal_year_start: date | None = None
    current_fiscal_year_end: date | None = None
    next_fiscal_year_start: date | None = None
    next_fiscal_year_end: date | None = None
    accounting_standard: str | None = None
    source_snapshot_id: str | None = None
    provenance_id: str | None = None
    normalizer_version: str = NORMALIZER_VERSION

    def __post_init__(self) -> None:
        if self.retrieved_at.tzinfo is None:
            raise ValueError("retrieved_at はtz-awareである必要があります")
        if self.market_public_at is not None and self.market_public_at.tzinfo is None:
            raise ValueError("market_public_at はtz-awareである必要があります")


@dataclass(kw_only=True, frozen=True)
class FundamentalMetric:
    """Financial Summary 1指標分。`raw_value`はProviderの生の値をそのまま保持し、
    `value`はParse後のTyped Value(`value_availability=PRESENT`の場合のみ非None)。

    `series_id`はRevision管理(`lib.evidence.model.RevisionHistory`)のSeries Keyで、
    同一entity・同一metric_type・同一fiscal_year_target・同一period_type・同一
    consolidation_scope・同一accounting_standardの組み合わせで構築する。
    """

    metric_id: str
    envelope_id: str
    series_id: str
    metric_type: str
    raw_value: str | None
    value: Decimal | None
    value_availability: ValueAvailability
    actual_or_forecast: ActualOrForecast
    fiscal_year_target: FiscalYearTarget
    period_type: PeriodType
    period_basis: PeriodBasis
    consolidation_scope: ConsolidationScope
    accounting_standard: str | None
    source_field: str
    currency: str | None = None
    unit: str | None = None
    source_disclosure_number: str | None = None
