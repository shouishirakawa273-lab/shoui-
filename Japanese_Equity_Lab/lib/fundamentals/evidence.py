"""Fundamental MetricからEvidenceを作る(Phase4A、D0043)。

Phase4Aでは「業績が良い」「Positive」「買い」等の解釈は禁止する。作れるのは
FACTのみ(例:「2024-08-09に会社がFY営業利益予想120を開示した」まで)。
「これはBullish」は作らない。`EvidenceRelation`(SUPPORTS/CONTRADICTS等)も、
Hypothesisが存在しない限り付与しない(RESEARCH_RULES.md「0.5」参照、DEFAULT
PROCESS = ADVERSARIAL、CONCLUSION = NEUTRAL UNTIL SUPPORTED)。

**Revision Wording上の注意(このRoundで修正)**: `disclosure_metric_to_
evidence()`は単一の`FundamentalMetric`(1つの開示された値)のみを引数に
取る。したがって「100→120へ変更した」のような旧→新の比較を含む文言は、
この関数からは生成できないし、生成すべきでもない — 単一Metricのみから
Revision Relationshipを推論することは禁止する(旧Value・新Value・同一
Metric・同一Fiscal Target/Scope・妥当な時系列順序・明示的/検証済みの
Revision関係、これらすべてが確認された場合のみ「変更した」と言える)。
このModuleが生成するFACTは常に「その値が開示された」という単一時点の
事実のみであり、新しいRevision Engineをこのモジュールへは追加しない。
"""

from __future__ import annotations

from datetime import datetime

from lib.evidence.model import DataLayer, EvidenceRecord, EvidenceType, SourceVersion
from lib.fundamentals.model import DisclosureEnvelope, FundamentalMetric
from lib.sources.catalog import DataCapability, PrimaryOrSecondary, SourceAuthorityClass, SourceMetadata

# 通貨/単位がRaw Payloadから未確認であることを明示するLabel(推測禁止、D0079)。
UNIT_STATUS_UNVERIFIED = "UNVERIFIED"

# A系統(MARKET_PUBLIC_AT)Bridgeが構築したEvidenceであることを示すTag
# (`SourceMetadata.source_type`は自由文字列であり、新しいSchema Fieldは
# 追加しない。`lib.evidence.research_artifact`がこの値でA/B混在を検知する)。
MARKET_PUBLIC_AT_SOURCE_TYPE = "JQUANTS_FINS_SUMMARY_MARKET_PUBLIC_AT"


def disclosure_metric_to_evidence(envelope: DisclosureEnvelope, metric: FundamentalMetric) -> EvidenceRecord:
    """開示された値そのものをFACTとして記述するのみ(解釈を加えない)。

    **PIT Bugfix(このRoundで修正、旧実装の問題点)**: 旧実装は
    `source.available_at = envelope.market_public_at or envelope.
    retrieved_at`としていた。これは`market_public_at`(市場公表時刻、
    A系統)を`available_at`(このProvider経由で研究所が実際に利用可能に
    なった時刻、B系統)へ紛れ込ませる誤り — `market_public_at`は
    `provider_available_at`より**早い**のが通常であり(会社が15:00に
    公表しても、Providerが実際に配信するのはそれ以降)、この早い時刻を
    `available_at`へ代入すると、実際にはまだ研究所側で取得可能でな
    かった時点を「利用可能だった」と誤認する(Future Leakage、旧
    Docstringの「保守的だから安全」という説明は論理が逆だった)。

    `DisclosureEnvelope`/`FundamentalMetric`/`SourceMetadata`のいずれも
    確認済みの`provider_available_at`(このProvider経由で実際に参照可能に
    なったTimestampをConfirmedとして保持するField)を持たない(現行
    Schemaの制約、`lib.fundamentals.model.DisclosureEnvelope`Docstring
    参照)。したがって`source.available_at`には常に`envelope.
    retrieved_at`(「少なくともこの時刻には研究所が取得済みだった」という
    Observed Fact)を使う。`market_public_at`は`source.published_at`
    (Market Information Study、A系統)としてのみ設定し、`available_at`へ
    Fallbackすることは禁止する(このBugfix以降の恒久的な原則)。

    一方、Fundamental Metric自体のRevision管理(`SourceVersion.
    availability_basis`)ほど厳密なUNKNOWN除外機構は`EvidenceRecord`には
    無い(既存D0040 Schemaの制約、`EVIDENCE_MODEL.md`参照)ため、厳密な
    B系統PIT判定には`lib.fundamentals.view.fundamentals_as_of()`を
    使うこと。
    """
    value_display = metric.raw_value if metric.raw_value is not None else metric.value_availability.value
    content = (
        f"{envelope.internal_code}: {metric.metric_type}"
        f"({metric.fiscal_year_target.value}, {metric.period_type.value}, "
        f"{metric.actual_or_forecast.value}, {metric.consolidation_scope.value})を"
        f"{value_display}として開示(disclosure_number={envelope.disclosure_number})"
    )
    # market_public_atへはFallbackしない(PIT Bugfix、上記Docstring参照)。
    # 確認済みprovider_available_atを保持するFieldが無いため、
    # retrieved_at(Observed Factとしての下限)を常に使う。
    available_at: datetime = envelope.retrieved_at
    source = SourceMetadata(
        source_id=envelope.envelope_id,
        source_type="JQUANTS_FINS_SUMMARY",
        provider_name="J-Quants",
        source_authority_class=SourceAuthorityClass.COMPANY_PRIMARY,
        primary_or_secondary=PrimaryOrSecondary.PRIMARY,
        retrieved_at=envelope.retrieved_at,
        published_at=envelope.market_public_at,
        available_at=available_at,
        originating_source="JQUANTS_SOURCE_DATA",  # 公式仕様で確認できた範囲のみ(D0043、DATA_SOURCE_ARCHITECTURE.md参照)
        delivery_provider="JQUANTS",
        provenance_id=envelope.provenance_id,
    )
    return EvidenceRecord(
        evidence_id=f"EVID_{metric.metric_id}",
        evidence_type=EvidenceType.FACT,
        layer=DataLayer.NORMALIZED,
        capability=DataCapability.FUNDAMENTAL,
        content=content,
        source=source,
        related_codes=(envelope.internal_code,),
        provenance_id=envelope.provenance_id,
    )


def source_version_to_evidence_market_public_at(version: SourceVersion, *, entity_code: str) -> EvidenceRecord:
    """A系統(Market Information Study、`AvailabilitySemantics.MARKET_PUBLIC_AT`)の
    選定済み`SourceVersion`をEvidence化する(D0072/D0074 Follow-up、Fundamentals
    A-Path Bridge)。

    **必ず`lib.fundamentals.view.fundamentals_as_of(availability_semantics=
    MARKET_PUBLIC_AT)`が選定した`SourceVersion`を渡すこと**(このRoundの
    設計上の要求)。生の`FundamentalMetric`全件を素通しでmarket_public_atへ
    変換してはいけない — `fundamentals_as_of()`の`RevisionHistory.
    as_of_by_semantics()`が`published_at <= decision_at`のCandidateのみに
    絞り込み、その中で最新のVersionを選ぶことで、Future Revision/Correctionが
    過去のas_ofへ漏れることを防ぐ(このBridge自身はas_of選択を行わない)。

    **UNKNOWN Timestampはfail closed**: `version.published_at`が`None`
    (=`market_public_at_basis=UNKNOWN`、DiscTime欠損等)の場合は例外にする。
    `fundamentals_as_of(availability_semantics=MARKET_PUBLIC_AT)`自体が
    `published_at is None`のVersionを既に候補から除外するため通常到達しない
    Guardだが、直接呼び出し等の誤用に備えて明示的に検証する。

    **B系統(`disclosure_metric_to_evidence()`)とは独立**: 生成される
    `available_at`はB系統の`envelope.retrieved_at`ではなく`version.
    published_at`そのもの(D0049は不変、`available_at`の生Fallback禁止は
    B系統のみに適用される既存の原則であり、この新しいA系統専用関数は
    別のSemanticsとして`source.published_at`をそのまま使う)。`source_type`
    に`MARKET_PUBLIC_AT_SOURCE_TYPE`を付与し、`build_research_artifact()`が
    A/B混在をfail closedで検知できるようにする。
    """
    if version.published_at is None:
        raise ValueError(
            f"source_version_id={version.source_version_id}: published_at(market_public_at)が"
            "UNKNOWNのVersionはA系統Evidenceにできません(fail closed、値を推測しない)"
        )
    content = f"{entity_code}: {version.source_record_id}={version.value}(market_public_at={version.published_at.isoformat()})"
    source = SourceMetadata(
        source_id=version.source_version_id,
        source_type=MARKET_PUBLIC_AT_SOURCE_TYPE,
        provider_name="J-Quants",
        source_authority_class=SourceAuthorityClass.COMPANY_PRIMARY,
        primary_or_secondary=PrimaryOrSecondary.PRIMARY,
        retrieved_at=version.retrieved_at,
        published_at=version.published_at,
        available_at=version.published_at,
        originating_source="JQUANTS_SOURCE_DATA",
        delivery_provider="JQUANTS",
        provenance_id=None,
    )
    return EvidenceRecord(
        evidence_id=f"EVID_A_{version.source_version_id}",
        evidence_type=EvidenceType.FACT,
        layer=DataLayer.NORMALIZED,
        capability=DataCapability.FUNDAMENTAL,
        content=content,
        source=source,
        related_codes=(entity_code,),
        provenance_id=None,
    )


def financial_quality_metric_to_evidence_market_public_at(
    version: SourceVersion, *, metric: FundamentalMetric, envelope: DisclosureEnvelope, entity_code: str
) -> EvidenceRecord:
    """Financial Quality系Metric(Stage 3.6: CFO/CFI/CFF)専用のA系統Evidence化。

    `source_version_to_evidence_market_public_at()`と同じA系統PIT Semantics
    (`published_at <= as_of`のCandidateからas_of時点最新のVersionを選ぶのは
    呼び出し側の`fundamentals_as_of(availability_semantics=MARKET_PUBLIC_AT)`、
    この関数自体はas_of選択を行わない。`available_at=version.published_at`、
    `source_type=MARKET_PUBLIC_AT_SOURCE_TYPE`)をそのまま再利用しつつ、
    対応する`FundamentalMetric`/`DisclosureEnvelope`を追加で受け取ることで、
    `content`へperiod_start/period_end/period_type/period_basis/
    consolidation_scope/accounting_standardを保持する(既存の軽量Bridgeは
    `source_record_id`=series_id文字列のみで、これらの一部(特にperiod_start/
    period_end)を保持していなかった)。

    **series_id文字列のfree-form parseはしない**: period_type/consolidation_
    scope/accounting_standard等は`metric`/`envelope`の型付きFieldから直接
    読む(series_idはSeries Keyとしてのみ扱う)。

    Unit/Currencyは`FundamentalMetric.currency`/`.unit`が実際に確認できた
    場合のみそれを使い、確認できていない場合は`UNIT_STATUS_UNVERIFIED`を
    明示する(値を推測しない、D0079要件)。

    **Defense-in-depth**: `metric.metric_id != version.source_version_id`
    または`metric.envelope_id != envelope.envelope_id`の場合、呼び出し側の
    入力自体が矛盾しているため`ValueError`にする(既存`build_latest_
    reported_fy_per()`と同様の設計)。
    """
    if version.published_at is None:
        raise ValueError(
            f"source_version_id={version.source_version_id}: published_at(market_public_at)が"
            "UNKNOWNのVersionはA系統Evidenceにできません(fail closed、値を推測しない)"
        )
    if metric.metric_id != version.source_version_id:
        raise ValueError(
            f"metric.metric_id({metric.metric_id})がversion.source_version_id({version.source_version_id})と一致しません"
        )
    if metric.envelope_id != envelope.envelope_id:
        raise ValueError(f"metric.envelope_id({metric.envelope_id})がenvelope.envelope_id({envelope.envelope_id})と一致しません")

    period_start = envelope.current_period_start.isoformat() if envelope.current_period_start is not None else "UNKNOWN"
    period_end = envelope.current_period_end.isoformat() if envelope.current_period_end is not None else "UNKNOWN"
    unit_status = metric.unit if metric.unit is not None else UNIT_STATUS_UNVERIFIED
    currency_status = metric.currency if metric.currency is not None else UNIT_STATUS_UNVERIFIED
    content = (
        f"{entity_code}: {metric.metric_type}(source_field={metric.source_field}, "
        f"period={period_start}..{period_end}, period_type={metric.period_type.value}, "
        f"period_basis={metric.period_basis.value}, consolidation_scope={metric.consolidation_scope.value}, "
        f"accounting_standard={metric.accounting_standard or 'UNKNOWN'}, "
        f"currency={currency_status}, unit={unit_status})="
        f"{version.value}(market_public_at={version.published_at.isoformat()})"
    )
    source = SourceMetadata(
        source_id=version.source_version_id,
        source_type=MARKET_PUBLIC_AT_SOURCE_TYPE,
        provider_name="J-Quants",
        source_authority_class=SourceAuthorityClass.COMPANY_PRIMARY,
        primary_or_secondary=PrimaryOrSecondary.PRIMARY,
        retrieved_at=version.retrieved_at,
        published_at=version.published_at,
        available_at=version.published_at,
        originating_source="JQUANTS_SOURCE_DATA",
        delivery_provider="JQUANTS",
        provenance_id=envelope.provenance_id,
    )
    return EvidenceRecord(
        evidence_id=f"EVID_A_FQ_{version.source_version_id}",
        evidence_type=EvidenceType.FACT,
        layer=DataLayer.NORMALIZED,
        capability=DataCapability.FUNDAMENTAL,
        content=content,
        source=source,
        related_codes=(entity_code,),
        value_date=envelope.current_period_end,
        provenance_id=envelope.provenance_id,
    )
