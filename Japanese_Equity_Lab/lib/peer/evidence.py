"""`PeerAggregateContext`をEvidence化する(Stage 3.17、D0095)。

`lib.valuation.historical_context_evidence`と同じ原則: FACTのみを記述し、
Interpretationを一切加えない。「Peer Median PERが8.0x」はFactだが
「だからTargetは割安」はInterpretationであり、この関数からは生成
できない・生成すべきでもない(禁止語Checkは呼び出し側Testで直接確認する)。

D0094が明示した教訓(「77 Evidence ≠ 77 independent confirmations」、
Evidence Countを膨らませることが情報の多様性を意味しない)を踏まえ、
Peer Comparisonは常に1件の集約EvidenceとしてResearchArtifactへ追加する
——Peerごとの個別Comparisonを1件ずつEvidence化しない(要件v1 §3)。
個々のPeer Metric Observationとのlineageは`lib.peer.provenance.
register_peer_context_provenance_bundle()`がProvenanceStore +
EvidenceRegistry経由で検証する。
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from lib.evidence.model import DataLayer, EvidenceRecord, EvidenceType
from lib.peer.model import PeerAggregateContext, PeerMetricType
from lib.registry.evidence_registry import EvidenceRegistry
from lib.registry.provenance import ProvenanceStore
from lib.sources.catalog import DataCapability, PrimaryOrSecondary, SourceAuthorityClass, SourceMetadata
from lib.valuation.evidence import is_latest_reported_fy_per_v2_evidence
from lib.valuation.model import SOURCE_ID_CURRENT_FY_COMPANY_FORECAST_PER

SOURCE_ID_PEER_VALUATION_CONTEXT = "PEER_VALUATION_CONTEXT"

_PEER_SET_FINGERPRINT_LENGTH = 16


def _peer_set_fingerprint(included_peer_entity_codes: tuple[str, ...]) -> str:
    """`included_peer_entity_codes`からCollision-Safeな16進Fingerprintを
    導出する(要件v1 §6)。

    Peer名を`"_".join(codes)`のように雑にConcatするだけの脆弱なIdentity
    (Peer件数が増えるとEvidence IDが線形に伸び続ける、順序が変わると
    別Identityになりうる)を避けるため、SHA-256のHex Digest先頭16文字を
    採用する。**計算式そのものを明示する(監査可能性、Codex-Ready
    Acceptance Surface)**: ``sha256(",".join(sorted(codes)).encode("utf-8"))
    .hexdigest()[:16]``。Peer Set(要素の集合)が同じであれば入力順序に
    依存せず同一Fingerprintになり、Peer Setが1件でも異なれば
    (実務上ほぼ確実に)異なるFingerprintになる。
    """
    joined = ",".join(sorted(included_peer_entity_codes))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:_PEER_SET_FINGERPRINT_LENGTH]


def _canonical_as_of_token(as_of: datetime) -> str:
    """`as_of`をUTCへCanonical Normalizeし、Date・Time・Microsecondまで
    失わないOS非依存のStable Tokenへ変換する(Stage 3.17.1、D0096
    Finding 4)。

    以前の実装は`record.as_of.date()`(日付のみ)をIdentityへ使っており、
    同日異時刻のContext(例: 2024-11-15 10:00 JSTと2024-11-15 15:00 JST)
    が衝突していた。`astimezone(UTC)`によって同一Instantは(元のTimezone
    Offset表記に関わらず)常に同一Tokenへ正規化される一方、異なるIntraday
    Instantは異なるTokenになる。コロン等ID中で扱いにくい文字を避けるため
    `%Y%m%dT%H%M%S.%fZ`(ISO 8601 Basic形式相当)を使う。
    """
    return as_of.astimezone(UTC).strftime("%Y%m%dT%H%M%S.%fZ")


def peer_valuation_context_evidence_id(record: PeerAggregateContext) -> str:
    """`PeerAggregateContext`のEvidence IDをDeterministicかつCollision-
    Safeに導出する(要件v1 §6、Stage 3.17.1 D0096 Finding 4で日付のみ
    からTimezone-Aware Full Timestampへ強化)。

    Identityへ反映する要素: target entity・metric・comparison as_of
    (Full Timestamp、Canonical UTC Token)・Peer Universe Selection
    Version・実際にIncludeされたPeer Set(Fingerprint経由)。同一target/
    as_ofでもPeer Setが異なるContextは異なるEvidence IDになる
    (`_peer_set_fingerprint()`参照)。同一Instantを指す異なるTimezone
    Offset表記のas_ofは同一Identityになる(`_canonical_as_of_token()`)。
    """
    fingerprint = _peer_set_fingerprint(record.included_peer_entity_codes)
    as_of_token = _canonical_as_of_token(record.as_of)
    return (
        f"EVID_{SOURCE_ID_PEER_VALUATION_CONTEXT}_{record.target_entity_code}_{record.metric_type.value}_"
        f"{as_of_token}_{record.selection_version}_{fingerprint}"
    )


def peer_valuation_context_to_evidence(
    record: PeerAggregateContext,
    *,
    source_authority_class: SourceAuthorityClass,
    originating_source: str,
    delivery_provider: str,
) -> EvidenceRecord:
    """`available_at`はRecordが既に保持する合成値(`lib.peer.builder.
    build_peer_aggregate_context()`が全Contributing Observationの
    `value_available_at`最大値として算出済み)をそのまま使う。

    `SourceMetadata.published_at`は`None`にする(`lib.valuation.
    historical_context_evidence`と同じ理由: この合成Derived Fact自体は
    独立したExternal Publication Eventを持たない)。

    Contentには"cheap"/"expensive"/"undervalued"/"overvalued"/
    "attractive"/BUY/SELL/rerating等のInterpretive語を一切含めない
    (要件v1 §3の禁止語リスト、実際の数値とMetadataのみを記述する)。
    """
    evidence_id = peer_valuation_context_evidence_id(record)
    content = (
        f"{record.target_entity_code}: PEER_VALUATION_CONTEXT("
        f"metric={record.metric_type.value}、as_of={record.as_of.isoformat()}、"
        f"cross_sectional_comparison=True、selection_version={record.selection_version})。"
        f"target_value={record.target_value}(evidence_id={record.target_observation_evidence_id})。"
        f"peer_count={record.peer_count}(minimum_sample_count={record.minimum_sample_count})、"
        f"included_peers={list(record.included_peer_entity_codes)}、"
        f"excluded_peers={list(record.excluded_peer_entity_codes)}。"
        f"peer_min={record.peer_min}、peer_median={record.peer_median}"
        f"(median_method={record.median_method})、peer_max={record.peer_max}。"
        f"target_percentile={record.target_percentile}"
        f"(percentile_method={record.percentile_method}、percentile_scale={record.percentile_scale})。"
    )
    source = SourceMetadata(
        source_id=evidence_id,
        source_type=SOURCE_ID_PEER_VALUATION_CONTEXT,
        provider_name=SOURCE_ID_PEER_VALUATION_CONTEXT,
        source_authority_class=source_authority_class,
        primary_or_secondary=PrimaryOrSecondary.PRIMARY,
        retrieved_at=record.available_at,
        published_at=None,
        available_at=record.available_at,
        originating_source=originating_source,
        delivery_provider=delivery_provider,
    )
    return EvidenceRecord(
        evidence_id=evidence_id,
        evidence_type=EvidenceType.FACT,
        layer=DataLayer.DERIVED,
        capability=DataCapability.PEER_COMPARISON,
        content=content,
        source=source,
        value_date=record.as_of.date(),
        related_codes=tuple(sorted({record.target_entity_code, *record.included_peer_entity_codes})),
    )


_PARENT_LINK_TYPE = "valuation_evidence"


def _metric_family_matches(evidence: EvidenceRecord, metric_type: PeerMetricType) -> bool:
    """`evidence`が実際に`metric_type`のValuation Metric Familyに由来する
    かを、既存Canonical Identity Helper/Constantで判定する(Stage 3.17.1、
    D0096 Finding 5)。文字列Contentの脆弱なParseはしない。"""
    if metric_type == PeerMetricType.LATEST_REPORTED_FY_PER:
        return is_latest_reported_fy_per_v2_evidence(evidence)
    if metric_type == PeerMetricType.CURRENT_FY_COMPANY_FORECAST_PER:
        return evidence.source.source_type == SOURCE_ID_CURRENT_FY_COMPANY_FORECAST_PER
    raise ValueError(f"未知のPeerMetricTypeです(fail closed): {metric_type!r}")  # pragma: no cover - Enum網羅


def verify_observation_parent_identity(
    evidence: EvidenceRecord, *, entity_code: str, metric_type: PeerMetricType, as_of_ceiling: datetime
) -> None:
    """1件のPeer Metric Observation Parent Evidenceが、期待する
    Entity・Metric Family・構造(FACT/DERIVED/VALUATION)・PITを満たすかを
    検証する(Stage 3.17.1、D0096 Finding 5)。

    `lib.peer.builder`のAdapter・`lib.peer.provenance.register_peer_
    context_provenance_bundle()`・本Module自身の`verify_peer_context_
    provenance()`の3箇所が同じCheckをCopy-Pasteしないよう、この1箇所へ
    集約する(D0096要件v1 §11「同じvalidation logicを3箇所へコピペ
    しない」)。**Wrong Valuation Metric Family Parent**(例:
    `LATEST_REPORTED_FY_PER` ObservationへCURRENT_FY_COMPANY_FORECAST_
    PER Evidenceが紐づく等)を、`entity`/`FACT`/`DERIVED`/`VALUATION`
    一致だけでは検出できなかった既存欠陥(D0095 Codex Finding 5)を
    ここで閉じる。
    """
    if as_of_ceiling.tzinfo is None:
        raise ValueError("as_of_ceiling はtz-awareである必要があります")
    problems: list[str] = []
    if evidence.evidence_type != EvidenceType.FACT:
        problems.append(f"evidence_type={evidence.evidence_type.value}(FACTが必要)")
    if evidence.layer != DataLayer.DERIVED:
        problems.append(f"layer={evidence.layer.value}(DERIVEDが必要)")
    if evidence.capability != DataCapability.VALUATION:
        problems.append(f"capability={evidence.capability.value}(VALUATIONが必要)")
    if entity_code not in evidence.related_codes:
        problems.append(f"related_codes={evidence.related_codes}(entity_code={entity_code}を含まない)")
    if not _metric_family_matches(evidence, metric_type):
        problems.append(
            f"source.source_type={evidence.source.source_type!r}がmetric_type={metric_type.value}の"
            "Canonical Source Typeと一致しません(Wrong Valuation Metric Family Parent、fail closed)"
        )
    if evidence.source.available_at > as_of_ceiling:
        problems.append(
            f"available_at={evidence.source.available_at.isoformat()}(as_of_ceiling={as_of_ceiling.isoformat()}より後)"
        )
    if problems:
        raise ValueError(
            f"evidence_id={evidence.evidence_id}: entity_code={entity_code}/metric_type={metric_type.value}の"
            f"Observation Parentとして不適格です(fail closed): {'; '.join(problems)}"
        )


def verify_peer_context_provenance(
    record: PeerAggregateContext,
    *,
    context_evidence_id: str,
    provenance_store: ProvenanceStore,
    evidence_registry: EvidenceRegistry,
) -> None:
    """Context Evidenceへ登録済みのProvenanceLinkが、Recordが保持する
    Parent Observation Evidence ID(target 1件 + included peer N件)と
    過不足なく一致するかを検証する(`lib.valuation.historical_context_
    evidence.verify_historical_context_provenance()`と同じ設計)。

    **Excluded PeerはSupporting Parentにしない(要件v1 §7)**:
    `record.excluded_peer_entity_codes`に対応するEvidenceは、そもそも
    `record.included_peer_observation_evidence_ids`に含まれないため、
    Expected Parent Set自体に現れない——このRecord自体の構造
    (`PeerAggregateContext.__post_init__`のDuplicate/Contamination
    Guard)がそれを保証する。

    **Parent Node Existence + Semantic Identity検証(Stage 3.17.1、D0096
    Finding 5)**: 全Parent IDについて、対応する`EvidenceRecord`が
    EvidenceRegistryに実在し、`verify_observation_parent_identity()`
    (Entity・Metric Family・FACT/DERIVED/VALUATION・PIT)を満たすことを
    検証する。
    """
    expected_parent_ids = {record.target_observation_evidence_id, *record.included_peer_observation_evidence_ids}

    links = provenance_store.parents_of(_PARENT_LINK_TYPE, context_evidence_id)
    registered_ids = [link.from_id for link in links]
    if len(set(registered_ids)) != len(registered_ids):
        duplicates = sorted({oid for oid in registered_ids if registered_ids.count(oid) > 1})
        raise ValueError(
            f"context_evidence_id={context_evidence_id}: ProvenanceLinkに重複したfrom_idがあります"
            f"(Duplicate Parent Guard): {duplicates}"
        )

    registered_set = set(registered_ids)
    missing = expected_parent_ids - registered_set
    unexpected = registered_set - expected_parent_ids
    if missing or unexpected:
        raise ValueError(
            f"context_evidence_id={context_evidence_id}: 登録済みParent LinkがRecordの"
            f"Observation Evidence IDと一致しません(fail closed、Fake/Dangling Lineage防止): "
            f"missing={sorted(missing)} unexpected={sorted(unexpected)}"
        )

    entity_by_evidence_id = {record.target_observation_evidence_id: record.target_entity_code}
    entity_by_evidence_id.update(
        zip(record.included_peer_observation_evidence_ids, record.included_peer_entity_codes, strict=True)
    )

    for parent_id in sorted(registered_set):
        parent_evidence = evidence_registry.get(parent_id)
        if parent_evidence is None:
            raise ValueError(
                f"context_evidence_id={context_evidence_id}: Parent evidence_id={parent_id}が"
                "EvidenceRegistryに存在しません(fail closed、架空/未登録IDへのLineageを許可しない)"
            )
        verify_observation_parent_identity(
            parent_evidence,
            entity_code=entity_by_evidence_id[parent_id],
            metric_type=record.metric_type,
            as_of_ceiling=record.as_of,
        )


__all__ = [
    "SOURCE_ID_PEER_VALUATION_CONTEXT",
    "peer_valuation_context_evidence_id",
    "peer_valuation_context_to_evidence",
    "verify_observation_parent_identity",
    "verify_peer_context_provenance",
]
