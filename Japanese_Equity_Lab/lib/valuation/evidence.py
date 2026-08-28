"""`LatestReportedFyPerRecord`をEvidence化する(D0077)。

Phase4A(Fundamentals)/Phase4C(Positioning)と同じ原則: FACTのみを記述し、
Interpretationを一切加えない。「7.29x」はFactだが「7.29xだから割安」は
Interpretationであり、この関数からは生成できない・生成すべきでもない
(禁止語チェックは呼び出し側Testで直接確認する)。
"""

from __future__ import annotations

from datetime import datetime

from lib.evidence.model import DataLayer, EvidenceRecord, EvidenceType
from lib.sources.catalog import DataCapability, PrimaryOrSecondary, SourceAuthorityClass, SourceMetadata
from lib.valuation.model import (
    SOURCE_ID,
    SOURCE_ID_CURRENT_FY_COMPANY_FORECAST_PER,
    CurrentFyCompanyForecastPerRecord,
    LatestReportedFyPerRecord,
)


def latest_reported_fy_per_evidence_id(record: LatestReportedFyPerRecord) -> str:
    """`latest_reported_fy_per_to_evidence()`が生成するevidence_idと同じ形式を返す
    (Stage 3.15、D0089)。

    Historical Valuation Context Builder(`lib.valuation.historical_context_
    builder`)がHistorical/Current PER Observationを一意に参照するIDとして
    このFormatをそのまま再利用する必要があるため、ID文字列組み立てロジックを
    ここへ1箇所化した(`latest_reported_fy_per_to_evidence()`側もこの関数を
    呼ぶよう変更し、二重実装しない)。
    """
    return f"EVID_{SOURCE_ID}_{record.entity_code}_{record.price_date.isoformat()}"


def latest_reported_fy_per_available_at(record: LatestReportedFyPerRecord) -> datetime:
    """`latest_reported_fy_per_to_evidence()`と同じavailable_at計算(要件v1-9、
    Price/Fundamentalsの両方が利用可能になった、より遅い方)を返す(Stage 3.15、
    D0089)。Historical Context Builderが個々のParent Recordから合成
    available_atを算出する際に、この定義をここへ1箇所化して再利用する。
    """
    return max(record.price_available_at, record.published_at)


def latest_reported_fy_per_to_evidence(
    record: LatestReportedFyPerRecord,
    *,
    source_authority_class: SourceAuthorityClass,
    originating_source: str,
    delivery_provider: str,
) -> EvidenceRecord:
    """`available_at`は2入力(Price/Fundamentals)が両方利用可能になった、最も遅い
    時刻を採用する(要件v1-9): ``max(record.price_available_at, record.
    published_at)``。

    **この方式を採用した理由(要件v1-9で要求された確認、意味的衝突は無いと
    判断した)**: `price_available_at`(`session_close_at`基準)は、この
    LabのPrice PITでは既にA/B系統の区別なく単一の可用性境界として扱われて
    いる(D0072のPositioning Evidence前例、`price_derived_record_to_
    evidence()`も同じ`session_close_at`をそのまま`available_at`に使う)。
    一方`record.published_at`はFundamentals A系統
    (`AvailabilitySemantics.MARKET_PUBLIC_AT`)の市場公表時刻そのもの
    (`build_latest_reported_fy_per()`は`SourceVersion.published_at`のみを
    使い、B系統の`retrieved_at`は一切参照しない)。両者とも「一般に公開
    された時刻」という共通の意味を持つため、遅い方を取ることが「両方が
    実際にPublicになった時刻」として意味的に整合する。D0049(B系統の
    `available_at`Fallback禁止)には抵触しない——このEvidence自体が
    B系統を名乗っていないため。
    """
    available_at = latest_reported_fy_per_available_at(record)
    content = (
        f"{record.entity_code}: {record.calculation_expression} = {record.multiple}"
        f"({record.metric_type}、{record.denominator_type}、"
        f"consolidation_scope={record.consolidation_scope}、"
        f"accounting_standard={record.accounting_standard or 'UNKNOWN'})"
    )
    source = SourceMetadata(
        source_id=f"{SOURCE_ID}_{record.entity_code}_{record.price_date.isoformat()}_{record.source_version_id}",
        source_type=SOURCE_ID,
        provider_name=SOURCE_ID,
        source_authority_class=source_authority_class,
        primary_or_secondary=PrimaryOrSecondary.PRIMARY,
        # このDerived Fact自体は独立したretrieved_at概念を持たない
        # (Price/EPSそれぞれのretrieved_atはRecordが保持しない、要件v1-6の
        # Field一覧参照)。下限としてavailable_atをそのまま使う。
        retrieved_at=available_at,
        published_at=record.published_at,
        available_at=available_at,
        originating_source=originating_source,
        delivery_provider=delivery_provider,
    )
    return EvidenceRecord(
        evidence_id=latest_reported_fy_per_evidence_id(record),
        evidence_type=EvidenceType.FACT,
        layer=DataLayer.DERIVED,
        capability=DataCapability.VALUATION,
        content=content,
        source=source,
        value_date=record.price_date,
        related_codes=(record.entity_code,),
    )


def current_fy_company_forecast_per_to_evidence(
    record: CurrentFyCompanyForecastPerRecord,
    *,
    source_authority_class: SourceAuthorityClass,
    originating_source: str,
    delivery_provider: str,
) -> EvidenceRecord:
    """`CurrentFyCompanyForecastPerRecord`をEvidence化する(Stage 3.10、D0084)。

    `latest_reported_fy_per_to_evidence()`(D0077、Actual FY Basis)と同じ
    原則(FACTのみ、Interpretation禁止)・同じ`available_at`方式(Price/
    Guidanceの両方が実際に利用可能になった、最も遅い時刻)を踏襲するが、
    `source_type`/`source_id`は`SOURCE_ID_CURRENT_FY_COMPANY_FORECAST_PER`
    を使い、Actual PER(`SOURCE_ID`)とは明確に区別する(genericな
    `FORWARD_PER`は使わない)。

    `available_at = max(record.price_available_at, record.guidance_
    published_at)`(要件v1-9と同じ考え方: Price PITはSession Close基準、
    Guidance PITはA系統`market_public_at`基準——いずれも「一般に公開された
    時刻」という共通の意味を持つため、遅い方を取ることが両方が実際に
    Publicになった時刻として意味的に整合する)。`value_date=record.
    price_date`(D0077と揃える)。Contentへは`forecast_period`/
    `disclosure_period_type`/`guidance_published_at`を明示的に含め、
    Forecast HorizonとDisclosure Cadenceを混同しない(D0083の区別を踏襲)。
    """
    available_at = max(record.price_available_at, record.guidance_published_at)
    content = (
        f"{record.entity_code}: {record.calculation_expression} = {record.multiple}"
        f"({record.metric_type}、{record.denominator_type}、"
        f"forecast_period={record.forecast_period_start.isoformat()}..{record.forecast_period_end.isoformat()}、"
        f"disclosure_period_type={record.disclosure_period_type}、"
        f"guidance_published_at={record.guidance_published_at.isoformat()}、"
        f"fiscal_year_target={record.fiscal_year_target}、"
        f"consolidation_scope={record.consolidation_scope}、"
        f"accounting_standard={record.accounting_standard or 'UNKNOWN'})"
    )
    source = SourceMetadata(
        source_id=(
            f"{SOURCE_ID_CURRENT_FY_COMPANY_FORECAST_PER}_{record.entity_code}_"
            f"{record.price_date.isoformat()}_{record.source_version_id}"
        ),
        source_type=SOURCE_ID_CURRENT_FY_COMPANY_FORECAST_PER,
        provider_name=SOURCE_ID_CURRENT_FY_COMPANY_FORECAST_PER,
        source_authority_class=source_authority_class,
        primary_or_secondary=PrimaryOrSecondary.PRIMARY,
        # このDerived Fact自体は独立したretrieved_at概念を持たない(D0077と同じ
        # 理由、Price/Guidanceそれぞれのretrieved_atはRecordが保持しない)。
        retrieved_at=available_at,
        published_at=record.guidance_published_at,
        available_at=available_at,
        originating_source=originating_source,
        delivery_provider=delivery_provider,
    )
    return EvidenceRecord(
        evidence_id=(f"EVID_{SOURCE_ID_CURRENT_FY_COMPANY_FORECAST_PER}_{record.entity_code}_{record.price_date.isoformat()}"),
        evidence_type=EvidenceType.FACT,
        layer=DataLayer.DERIVED,
        capability=DataCapability.VALUATION,
        content=content,
        source=source,
        value_date=record.price_date,
        related_codes=(record.entity_code,),
    )


__all__ = [
    "current_fy_company_forecast_per_to_evidence",
    "latest_reported_fy_per_available_at",
    "latest_reported_fy_per_evidence_id",
    "latest_reported_fy_per_to_evidence",
]
