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

from lib.evidence.model import DataLayer, EvidenceRecord, EvidenceType
from lib.fundamentals.model import DisclosureEnvelope, FundamentalMetric
from lib.sources.catalog import DataCapability, PrimaryOrSecondary, SourceAuthorityClass, SourceMetadata


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
