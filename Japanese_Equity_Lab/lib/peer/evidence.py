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

from lib.evidence.model import DataLayer, EvidenceRecord, EvidenceType
from lib.peer.model import PeerAggregateContext
from lib.registry.evidence_registry import EvidenceRegistry
from lib.registry.provenance import ProvenanceStore
from lib.sources.catalog import DataCapability, PrimaryOrSecondary, SourceAuthorityClass, SourceMetadata

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


def peer_valuation_context_evidence_id(record: PeerAggregateContext) -> str:
    """`PeerAggregateContext`のEvidence IDをDeterministicかつCollision-
    Safeに導出する(要件v1 §6)。

    Identityへ反映する要素: target entity・metric・comparison as_of・
    Peer Universe Selection Version・実際にIncludeされたPeer Set
    (Fingerprint経由)。同一target/as_ofでもPeer Setが異なるContextは
    異なるEvidence IDになる(`_peer_set_fingerprint()`参照)。
    """
    fingerprint = _peer_set_fingerprint(record.included_peer_entity_codes)
    return (
        f"EVID_{SOURCE_ID_PEER_VALUATION_CONTEXT}_{record.target_entity_code}_{record.metric_type.value}_"
        f"{record.as_of.date().isoformat()}_{record.selection_version}_{fingerprint}"
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

    **Parent Node Existence検証**: 全Parent IDについて、対応する
    `EvidenceRecord`がEvidenceRegistryに実在し、`EvidenceType.FACT`・
    `DataLayer.DERIVED`・`DataCapability.VALUATION`(Peer Metric
    Observationは常に既存Valuation Family、`lib.valuation.evidence`由来)・
    `available_at <= record.as_of`を満たすことを検証する。
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

    for parent_id in sorted(registered_set):
        parent_evidence = evidence_registry.get(parent_id)
        if parent_evidence is None:
            raise ValueError(
                f"context_evidence_id={context_evidence_id}: Parent evidence_id={parent_id}が"
                "EvidenceRegistryに存在しません(fail closed、架空/未登録IDへのLineageを許可しない)"
            )
        problems: list[str] = []
        if parent_evidence.evidence_type != EvidenceType.FACT:
            problems.append(f"evidence_type={parent_evidence.evidence_type.value}(FACTが必要)")
        if parent_evidence.layer != DataLayer.DERIVED:
            problems.append(f"layer={parent_evidence.layer.value}(DERIVEDが必要)")
        if parent_evidence.capability != DataCapability.VALUATION:
            problems.append(f"capability={parent_evidence.capability.value}(VALUATIONが必要)")
        if parent_evidence.source.available_at > record.as_of:
            problems.append(
                f"available_at={parent_evidence.source.available_at.isoformat()}(as_of={record.as_of.isoformat()}より後)"
            )
        if problems:
            raise ValueError(
                f"context_evidence_id={context_evidence_id}: Parent evidence_id={parent_id}が"
                f"Peer Context Parentとして不適格です(fail closed): {'; '.join(problems)}"
            )


__all__ = [
    "SOURCE_ID_PEER_VALUATION_CONTEXT",
    "peer_valuation_context_evidence_id",
    "peer_valuation_context_to_evidence",
    "verify_peer_context_provenance",
]
