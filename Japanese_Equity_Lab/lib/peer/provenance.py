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

from lib.evidence.model import EvidenceRecord
from lib.peer.evidence import peer_valuation_context_evidence_id, verify_observation_parent_identity
from lib.peer.model import PeerAggregateContext, PeerMetricType
from lib.registry.evidence_registry import EvidenceRegistry
from lib.registry.provenance import ProvenanceLink, ProvenanceStore
from lib.valuation.evidence import latest_reported_fy_per_available_at, latest_reported_fy_per_evidence_id_v2
from lib.valuation.model import LatestReportedFyPerRecord
from lib.valuation.provenance import register_latest_reported_fy_per_upstream_provenance

_PARENT_LINK_TYPE = "valuation_evidence"


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

    **全Validationを最初のWriteより前に完了させる(Stage 3.17.1、D0096
    Finding 6)**: 以前は`latest_reported_fy_per_records_by_entity`の
    整合性(余分なEntity・`record.entity_code`とMapping Keyの不一致)を
    第1階層Link書き込み後に検証しており、後段Validation失敗時に
    Partial Provenance Bundleが残り得た。D0096では、Write可能な事前
    Check(Context Evidence Identity・Registry実在・target/included
    peer Parent実在・Duplicate Parent・Parent Semantic Identity・
    Optional Upstream Mapping Entity集合・Mapping Keyと`record.
    entity_code`の一致)を全て`provenance_store.add_link()`より前で
    完了させる。ProvenanceStore自体へTransaction機構を新設するわけでは
    なく(Scope外)、既存Upstream Helper内部の予期不能I/O Failureまで
    Rollbackする設計も導入しない——このHelper自身が事前に判定可能な
    事項のみを前倒しする。

    **Parent Semantic Identity(D0096 Finding 5)**: 各Observation
    Parentは`verify_observation_parent_identity()`(`lib.peer.evidence`
    に集約、Adapter・本関数・`verify_peer_context_provenance()`で共有)
    により、Entity・Metric Family(`context_record.metric_type`)・
    FACT/DERIVED/VALUATION・PITを検証する。

    **Optional Upstream Recordの Canonical Record/Evidence一致(Stage
    3.17.2、D0097 Finding 6)**: D0096時点では、`latest_reported_fy_
    per_records_by_entity`の各`record`が「登録済みObservation Evidence
    と実際に対応するSource Version(Disclosure)か」までは、Phase 1では
    検証していなかった(Entity一致のみ)。そのため、同一Entityでも
    `source_version_id`が異なるRecord(=別Disclosure)が渡されても、
    既存Upstream Helper内部のCheckがPhase 2(Write後)で走るまで検出
    できなかった(D0096 Codex Re-Audit Finding 6)。D0097では、既存
    Canonical ID Helper(`latest_reported_fy_per_evidence_id_v2()`)と
    `latest_reported_fy_per_available_at()`をそのまま再利用し、この
    `record`から導出される期待Evidence ID/available_atが、登録済み
    Observation Evidenceと完全一致することをPhase 1(Writeより前)で
    検証する(新しいIdentity Algorithmは作らない)。
    """
    # ---- Phase 1: Writeなしで判定可能な全Validation ----
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

    entity_to_evidence_id: dict[str, str] = {context_record.target_entity_code: context_record.target_observation_evidence_id}
    for code, evidence_id in zip(
        context_record.included_peer_entity_codes, context_record.included_peer_observation_evidence_ids, strict=True
    ):
        entity_to_evidence_id[code] = evidence_id

    parent_evidence_by_id: dict[str, EvidenceRecord] = {}
    for entity_code, evidence_id in entity_to_evidence_id.items():
        parent_evidence = evidence_registry.get(evidence_id)
        if parent_evidence is None:
            raise ValueError(
                f"evidence_id={evidence_id}がEvidenceRegistryに存在しません"
                "(Fake Parent Evidence、fail closed。事前にEvidenceRegistryへ登録してください)"
            )
        verify_observation_parent_identity(
            parent_evidence, entity_code=entity_code, metric_type=context_record.metric_type, as_of_ceiling=context_record.as_of
        )
        parent_evidence_by_id[evidence_id] = parent_evidence

    # Optional Upstream Mapping(第2階層候補)自体の整合性も、第1階層Write前に検証する
    # (D0096 Finding 6: 「余分なEntity」「record.entity_code != Mapping Key」は
    # Writeなしで判定可能なため、ここで完了させる)。
    do_upstream = bool(latest_reported_fy_per_records_by_entity) and (
        context_record.metric_type == PeerMetricType.LATEST_REPORTED_FY_PER
    )
    if latest_reported_fy_per_records_by_entity:
        for entity_code, record in latest_reported_fy_per_records_by_entity.items():
            if entity_code not in entity_to_evidence_id:
                raise ValueError(
                    f"entity_code={entity_code}はcontext_recordのtarget/included peerのいずれでもありません"
                    "(latest_reported_fy_per_records_by_entityに余分なEntityが含まれています、fail closed)"
                )
            if record.entity_code != entity_code:
                raise ValueError(
                    f"latest_reported_fy_per_records_by_entity[{entity_code!r}].entity_code({record.entity_code})が"
                    f"Mapping Key({entity_code})と一致しません(fail closed)"
                )
            # Stage 3.17.2(D0097 Finding 6): 「record.entity_codeがMapping Keyと一致する」
            # だけでは、同一EntityでもSource Version(=Disclosure)が異なるRecordが渡され、
            # 既に登録済みのObservation Evidenceと実際には対応していないケースを検出でき
            # ない(既存Upstream Helper内部のCheckはPhase 2=Write後にしか走らなかった、
            # D0096 Codex Re-Audit Finding 6)。既存Canonical ID Helper(`latest_reported_
            # fy_per_evidence_id_v2()`)をそのまま再利用し、この`record`から導出される
            # 期待Evidence IDが、Context側が実際に保持するObservation Evidence IDと
            # 完全一致することをWriteより前に検証する(新しいIdentity Algorithmは作らない)。
            if context_record.metric_type == PeerMetricType.LATEST_REPORTED_FY_PER:
                expected_observation_evidence_id = latest_reported_fy_per_evidence_id_v2(record)
                registered_observation_evidence_id = entity_to_evidence_id[entity_code]
                if expected_observation_evidence_id != registered_observation_evidence_id:
                    raise ValueError(
                        f"entity_code={entity_code}: latest_reported_fy_per_records_by_entityのrecordから"
                        f"導出される期待Evidence ID({expected_observation_evidence_id})が、登録済み"
                        f"Observation Evidence ID({registered_observation_evidence_id})と一致しません"
                        "(Canonical Record/Evidence Mismatch、fail closed、Write前に検出)"
                    )
                registered_observation_evidence = parent_evidence_by_id[registered_observation_evidence_id]
                expected_available_at = latest_reported_fy_per_available_at(record)
                if registered_observation_evidence.source.available_at != expected_available_at:
                    raise ValueError(
                        f"entity_code={entity_code}: recordから導出される期待available_at"
                        f"({expected_available_at.isoformat()})が、登録済みObservation Evidenceのavailable_at"
                        f"({registered_observation_evidence.source.available_at.isoformat()})と一致しません"
                        "(fail closed、Write前に検出)"
                    )

    # ---- Phase 2: Write ----
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

    if do_upstream and latest_reported_fy_per_records_by_entity:
        for entity_code, record in latest_reported_fy_per_records_by_entity.items():
            observation_evidence_id = entity_to_evidence_id[entity_code]
            observation_evidence = parent_evidence_by_id[observation_evidence_id]
            register_latest_reported_fy_per_upstream_provenance(
                record=record, evidence=observation_evidence, provenance_store=provenance_store
            )


__all__ = ["register_peer_context_provenance_bundle"]
