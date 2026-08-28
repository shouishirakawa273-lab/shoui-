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
    """`latest_reported_fy_per_to_evidence()`(既存D0077 Evidence ID、v1)が
    生成するevidence_idと同じ形式を返す(Stage 3.15、D0089)。

    **既知の制約(Stage 3.15.1、D0090で特定): Identity Collision Risk**:
    このID形式(`entity_code` + `price_date`のみ)は、同一`price_date`だが
    異なる`source_version_id`(例: EPSの訂正・別Fiscal Year Denominatorへの
    切替)を持つ2つのDistinctなFactを区別できない。この関数自体は既に
    `02_company_research/7203_Toyota_Motor/research_artifacts.jsonl`
    (実際に永続化済みのResearchArtifact)から参照されているため、Silentに
    意味を変更しない(D0090要件v1 §13、Backward Compatibility)。新規に
    Identity Collisionを気にする用途(Historical Valuation Context等)では
    `latest_reported_fy_per_evidence_id_v2()`を使うこと。
    """
    return f"EVID_{SOURCE_ID}_{record.entity_code}_{record.price_date.isoformat()}"


def latest_reported_fy_per_evidence_id_v2(record: LatestReportedFyPerRecord) -> str:
    """LATEST_REPORTED_FY_PER Evidence ID v2(Stage 3.15.1、D0090、Collision-Safe
    Identity)。

    v1(`latest_reported_fy_per_evidence_id()`)は`entity_code` + `price_date`
    のみでIdentityを構成しており、同一`price_date`で異なる`source_version_id`
    (異なるFY Denominator、またはEPS訂正)を持つ2つのDistinctなFactが衝突
    し得る。`source_version_id`をIdentityへ追加することで、これらを区別
    可能にする。

    **`as_of`をIdentityへ含めない理由(確認済み)**: `as_of`はQuery Context
    (「いつ問い合わせたか」)であり、Fact自体の内容(Price/EPS/計算結果)を
    決めない——同一の`price_date`・`source_version_id`のRecordは、どの
    `as_of`から`build_latest_reported_fy_per()`を呼んでも常に同一の
    `multiple`を返す(Builder自体がDeterministicなため)。したがって`as_of`
    はIdentityに不要と判断した。

    **`corporate_action_basis_status`をIdentityへ含めない理由**: 実際に
    構築される`LatestReportedFyPerRecord`は、Corporate Action Guardに
    より`None`を返すか(Recordが存在しない)、`CorporateActionBasisStatus.
    CONFIRMED_NO_ACTION`のいずれかにしかならない(`lib.valuation.model`
    Docstring参照、現状唯一の値)。したがって現行Schemaでは区別すべき
    別の値が存在せず、Identityへ追加する意味が無い。

    v1 IDとは異なるPrefix(`_V2_`)を持つため、v1/v2が同じPrefixで意味だけ
    Silentに変わる事態を避けている(D0090要件v1 §13)。
    """
    return f"EVID_{SOURCE_ID}_V2_{record.entity_code}_{record.price_date.isoformat()}_{record.source_version_id}"


def latest_reported_fy_per_available_at(record: LatestReportedFyPerRecord) -> datetime:
    """`latest_reported_fy_per_to_evidence()`と同じavailable_at計算(要件v1-9、
    Price/Fundamentalsの両方が利用可能になった、より遅い方)を返す(Stage 3.15、
    D0089)。Historical Context Builderが個々のParent Recordから合成
    available_atを算出する際に、この定義をここへ1箇所化して再利用する。
    """
    return max(record.price_available_at, record.published_at)


def _build_latest_reported_fy_per_evidence(
    record: LatestReportedFyPerRecord,
    *,
    evidence_id: str,
    source_authority_class: SourceAuthorityClass,
    originating_source: str,
    delivery_provider: str,
) -> EvidenceRecord:
    """`latest_reported_fy_per_to_evidence()`(v1)/`latest_reported_fy_per_to_
    evidence_v2()`(Stage 3.15.1、D0090)が共有するEvidence構築ロジック。
    `evidence_id`のみ呼び出し側(v1/v2)が指定し、それ以外(`available_at`
    計算・Content・SourceMetadata)は完全に共通(二重実装しない)。

    `available_at`は2入力(Price/Fundamentals)が両方利用可能になった、最も遅い
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
        evidence_id=evidence_id,
        evidence_type=EvidenceType.FACT,
        layer=DataLayer.DERIVED,
        capability=DataCapability.VALUATION,
        content=content,
        source=source,
        value_date=record.price_date,
        related_codes=(record.entity_code,),
    )


def latest_reported_fy_per_to_evidence(
    record: LatestReportedFyPerRecord,
    *,
    source_authority_class: SourceAuthorityClass,
    originating_source: str,
    delivery_provider: str,
) -> EvidenceRecord:
    """既存D0077 Evidence(v1、`evidence_id`は`latest_reported_fy_per_evidence_
    id()`)。**既に永続化済みのResearchArtifactから参照されているため、この
    関数の出力(evidence_id含む)はSilentに変更しない**(D0090要件v1 §13)。
    Identity Collisionを気にする新規用途は`latest_reported_fy_per_to_
    evidence_v2()`を使うこと。
    """
    return _build_latest_reported_fy_per_evidence(
        record,
        evidence_id=latest_reported_fy_per_evidence_id(record),
        source_authority_class=source_authority_class,
        originating_source=originating_source,
        delivery_provider=delivery_provider,
    )


def latest_reported_fy_per_to_evidence_v2(
    record: LatestReportedFyPerRecord,
    *,
    source_authority_class: SourceAuthorityClass,
    originating_source: str,
    delivery_provider: str,
) -> EvidenceRecord:
    """LATEST_REPORTED_FY_PER Evidence v2(Stage 3.15.1、D0090、Collision-Safe
    Identity)。`evidence_id`は`latest_reported_fy_per_evidence_id_v2()`
    (`entity_code` + `price_date` + `source_version_id`)。それ以外の
    Field(Content/SourceMetadata/available_at)はv1と完全に同一(`_build_
    latest_reported_fy_per_evidence()`を共有)。Historical Valuation Context
    (`lib.valuation.historical_context_builder`)が新規に構築するPER Parent
    Evidenceはこちらを使う。
    """
    return _build_latest_reported_fy_per_evidence(
        record,
        evidence_id=latest_reported_fy_per_evidence_id_v2(record),
        source_authority_class=source_authority_class,
        originating_source=originating_source,
        delivery_provider=delivery_provider,
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
    "latest_reported_fy_per_evidence_id_v2",
    "latest_reported_fy_per_to_evidence",
    "latest_reported_fy_per_to_evidence_v2",
]
