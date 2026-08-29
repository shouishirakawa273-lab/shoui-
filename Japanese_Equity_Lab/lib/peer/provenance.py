"""Peer Context Evidenceに関するProvenance Edge永続化Helper(Stage 3.17、
D0095)。

Desired DAG(要件v1 §4):

```
Peer Context Evidence
  -> Target Metric Observation Evidence
  -> Peer A Metric Observation Evidence
  -> Peer B Metric Observation Evidence
  -> ...
       -> (可能な範囲で)既存 Price / Fundamental Source Version
```

**架空Evidence IDをParentとして登録しない**: 全Parent(target 1件 +
included peer N件)が`evidence_registry`に実在することを、書き込み前に
検証する(既存`lib.valuation.provenance.register_historical_context_
provenance_bundle()`と同じ「全Validationを書き込み前に完了させる」方針)。

**第2階層(Observation Evidence -> Price/EPS Raw Lineage)の限界**:
既存`lib.valuation.provenance.register_latest_reported_fy_per_upstream_
provenance()`は`LatestReportedFyPerRecord`(Metric=`LATEST_REPORTED_
FY_PER`)専用であり、`CurrentFyCompanyForecastPerRecord`(Metric=
`CURRENT_FY_COMPANY_FORECAST_PER`)向けの同等Helperは現状Repositoryに
存在しない。**存在しないHelperをこのRoundで新設することはScope外**
(要件v1 §9「新しいValuation計算Logicは作らない」)——したがって
`CURRENT_FY_COMPANY_FORECAST_PER`のPeer Contextについては、この関数は
第1階層(Context -> Observation Evidence)のみを配線し、第2階層は行わない
(架空のProvenanceを主張しない、fail closedではなく「単に実行しない」)。
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from lib.evidence.model import DataLayer, EvidenceRecord, EvidenceType
from lib.peer.evidence import peer_valuation_context_evidence_id
from lib.peer.model import PeerAggregateContext, PeerMetricType
from lib.registry.evidence_registry import EvidenceRegistry
from lib.registry.provenance import ProvenanceLink, ProvenanceStore
from lib.sources.catalog import DataCapability
from lib.valuation.model import LatestReportedFyPerRecord
from lib.valuation.provenance import register_latest_reported_fy_per_upstream_provenance

_PARENT_LINK_TYPE = "valuation_evidence"


def _validate_observation_parent(
    evidence_id: str, *, evidence_registry: EvidenceRegistry, as_of_ceiling: datetime
) -> EvidenceRecord:
    parent_evidence = evidence_registry.get(evidence_id)
    if parent_evidence is None:
        raise ValueError(
            f"evidence_id={evidence_id}がEvidenceRegistryに存在しません"
            "(Fake Parent Evidence、fail closed。事前にEvidenceRegistryへ登録してください)"
        )
    problems: list[str] = []
    if parent_evidence.evidence_type != EvidenceType.FACT:
        problems.append(f"evidence_type={parent_evidence.evidence_type.value}(FACTが必要)")
    if parent_evidence.layer != DataLayer.DERIVED:
        problems.append(f"layer={parent_evidence.layer.value}(DERIVEDが必要)")
    if parent_evidence.capability != DataCapability.VALUATION:
        problems.append(f"capability={parent_evidence.capability.value}(VALUATIONが必要)")
    if parent_evidence.source.available_at > as_of_ceiling:
        problems.append(f"available_at={parent_evidence.source.available_at.isoformat()}(as_of_ceilingより後)")
    if problems:
        raise ValueError(f"evidence_id={evidence_id}がPeer Context Parentとして不適格です(fail closed): {'; '.join(problems)}")
    return parent_evidence


def register_peer_context_provenance_bundle(
    *,
    context_record: PeerAggregateContext,
    context_evidence: EvidenceRecord,
    evidence_registry: EvidenceRegistry,
    provenance_store: ProvenanceStore,
    latest_reported_fy_per_records_by_entity: Mapping[str, LatestReportedFyPerRecord] | None = None,
) -> None:
    """`PeerAggregateContext`のFull Provenance Wiringを1回の呼び出しで行う。

    1. Context -> Observation Evidence(target 1件 + included peer N件、
       常に配線する)。
    2. Observation Evidence -> Price/EPS Raw Lineage(`context_record.
       metric_type == PeerMetricType.LATEST_REPORTED_FY_PER`かつ呼び出し
       側が対応する`LatestReportedFyPerRecord`を`latest_reported_fy_per_
       records_by_entity`で渡した場合のみ、既存`register_latest_
       reported_fy_per_upstream_provenance()`をそのまま再利用して実行
       する。それ以外(Metric不一致、またはRecordが渡されなかったEntity)
       は第2階層を行わない——架空のProvenanceを主張しない)。

    **全Validationを書き込み前に完了させる(Partial Write回避)**。
    """
    expected_evidence_id = peer_valuation_context_evidence_id(context_record)
    if context_evidence.evidence_id != expected_evidence_id:
        raise ValueError(
            f"context_evidence.evidence_id({context_evidence.evidence_id})がcontext_recordから導出される"
            f"期待ID({expected_evidence_id})と一致しません(fail closed)"
        )
    if evidence_registry.get(context_evidence.evidence_id) is None:
        raise ValueError(
            f"context_evidence_id={context_evidence.evidence_id}がEvidenceRegistryに存在しません"
            "(先にEvidenceRegistryへ登録してください)"
        )

    all_observation_evidence_ids = (
        context_record.target_observation_evidence_id,
        *context_record.included_peer_observation_evidence_ids,
    )
    if len(set(all_observation_evidence_ids)) != len(all_observation_evidence_ids):
        raise ValueError(
            f"context_evidence_id={context_evidence.evidence_id}: target_observation_evidence_idと"
            "included_peer_observation_evidence_idsに重複があります(Duplicate Parent Guard)"
        )

    for evidence_id in all_observation_evidence_ids:
        _validate_observation_parent(evidence_id, evidence_registry=evidence_registry, as_of_ceiling=context_record.as_of)

    for evidence_id in all_observation_evidence_ids:
        provenance_store.add_link(
            ProvenanceLink(
                link_id=f"L_PEERCTX_{context_evidence.evidence_id}_{evidence_id}",
                from_type=_PARENT_LINK_TYPE,
                from_id=evidence_id,
                to_type=_PARENT_LINK_TYPE,
                to_id=context_evidence.evidence_id,
            )
        )

    if not latest_reported_fy_per_records_by_entity:
        return
    if context_record.metric_type != PeerMetricType.LATEST_REPORTED_FY_PER:
        # CURRENT_FY_COMPANY_FORECAST_PER等、既存Upstream Helperが存在しないMetricでは
        # 第2階層を行わない(架空のProvenanceを主張しない、fail closedではなく「実行しない」)。
        return

    entity_to_evidence_id: dict[str, str] = {context_record.target_entity_code: context_record.target_observation_evidence_id}
    for code, evidence_id in zip(
        context_record.included_peer_entity_codes, context_record.included_peer_observation_evidence_ids, strict=True
    ):
        entity_to_evidence_id[code] = evidence_id

    for entity_code, record in latest_reported_fy_per_records_by_entity.items():
        if entity_code not in entity_to_evidence_id:
            raise ValueError(
                f"entity_code={entity_code}はcontext_recordのtarget/included peerのいずれでもありません"
                "(latest_reported_fy_per_records_by_entityに余分なEntityが含まれています)"
            )
        observation_evidence_id = entity_to_evidence_id[entity_code]
        observation_evidence = evidence_registry.require(observation_evidence_id)
        register_latest_reported_fy_per_upstream_provenance(
            record=record, evidence=observation_evidence, provenance_store=provenance_store
        )


__all__ = ["register_peer_context_provenance_bundle"]
