"""LATEST_REPORTED_FY_PER Evidenceに関するProvenance Edge永続化Helper
(Stage 3.15.3、D0092)。

D0091 Real Acceptanceでは、PER→Price/PER→EPSのProvenance Edge永続化を
Orchestration Scratch Scriptが直接手書きしていた(`ProvenanceStore.add_
link()`を都度呼ぶだけ)。Repositoryに正式なProduction Helperが存在せず、
Real Acceptance Runごとに再実装されるリスクがあったため、このModuleへ
最小限のHelperをCommitする。

**Genericな Provenance/Graph Frameworkは作らない**: 既存`lib.registry.
provenance.ProvenanceStore`/`ProvenanceLink`をそのまま再利用し、新しい
永続化機構・新しいID体系は追加しない。Price/EPSのNatural Key(`lib.
valuation.builder`のTest群、D0077以来のPattern)もそのまま踏襲する。
"""

from __future__ import annotations

from collections.abc import Sequence

from lib.evidence.model import DataLayer, EvidenceRecord, EvidenceType
from lib.registry.evidence_registry import EvidenceRegistry
from lib.registry.provenance import ProvenanceLink, ProvenanceStore
from lib.sources.catalog import DataCapability
from lib.valuation.evidence import (
    is_latest_reported_fy_per_v2_evidence,
    latest_reported_fy_per_available_at,
    latest_reported_fy_per_evidence_id_v2,
)
from lib.valuation.historical_context_evidence import verify_historical_context_provenance
from lib.valuation.model import LatestReportedFyPerHistoricalContextRecord, LatestReportedFyPerRecord

_PARENT_LINK_TO_TYPE = "valuation_evidence"
_PRICE_FROM_TYPE = "price_bar"
_EPS_FROM_TYPE = "fundamental_source_version"


def _validate_latest_reported_fy_per_evidence(*, record: LatestReportedFyPerRecord, evidence: EvidenceRecord) -> None:
    """`evidence`が実際に`record`から構築されたv2 Evidenceであることをfail closedで
    検証する(Provenance Edgeを書き込む前の共通Pre-condition)。"""
    problems: list[str] = []
    if evidence.evidence_type != EvidenceType.FACT:
        problems.append(f"evidence_type={evidence.evidence_type.value}(FACTが必要)")
    if evidence.layer != DataLayer.DERIVED:
        problems.append(f"layer={evidence.layer.value}(DERIVEDが必要)")
    if evidence.capability != DataCapability.VALUATION:
        problems.append(f"capability={evidence.capability.value}(VALUATIONが必要)")
    if record.entity_code not in evidence.related_codes:
        problems.append(f"related_codes={evidence.related_codes}(entity_code={record.entity_code}を含まない)")
    if not is_latest_reported_fy_per_v2_evidence(evidence):
        problems.append("v1 EvidenceまたはLATEST_REPORTED_FY_PER以外のEvidenceです(v2のみ許可)")
    else:
        expected_id = latest_reported_fy_per_evidence_id_v2(record)
        if evidence.evidence_id != expected_id:
            problems.append(f"evidence_id={evidence.evidence_id}がrecordから導出される期待ID({expected_id})と一致しません")
        expected_available_at = latest_reported_fy_per_available_at(record)
        if evidence.source.available_at != expected_available_at:
            problems.append(
                f"available_at={evidence.source.available_at.isoformat()}が recordから導出される期待値"
                f"({expected_available_at.isoformat()})と一致しません"
            )
    if problems:
        raise ValueError(
            f"evidence_id={evidence.evidence_id}はrecord(entity_code={record.entity_code}、"
            f"price_date={record.price_date.isoformat()})に対応するValid PER Evidenceではありません"
            f"(fail closed): {'; '.join(problems)}"
        )


def register_latest_reported_fy_per_upstream_provenance(
    *,
    record: LatestReportedFyPerRecord,
    evidence: EvidenceRecord,
    provenance_store: ProvenanceStore,
) -> None:
    """1件のLATEST_REPORTED_FY_PER v2 Evidenceについて、Price/EPS Upstream
    Provenance Edgeを`ProvenanceStore`へ永続化する(既存D0077 Natural-Key
    Pattern、`test_valuation_evidence_traces_to_both_price_and_eps_
    parents`をそのまま再利用)。

    Price Parent: `from_type="price_bar"`、`from_id=f"{entity_code}:
    {price_date}"`。EPS Parent: `from_type="fundamental_source_version"`、
    `from_id=source_version_id`。Target: `from_type="valuation_evidence"`、
    `to_id=evidence.evidence_id`。

    **Duplicate Semantics**: `link_id`は`evidence.evidence_id`から
    Deterministicに導出するため、同一Evidenceへ対して2回呼び出すと
    既存`ProvenanceStore.add_link()`の`AppendOnlyViolationError`が
    そのまま伝播する(Silent Upsertしない、新しいException Typeは
    追加しない)。
    """
    _validate_latest_reported_fy_per_evidence(record=record, evidence=evidence)
    provenance_store.add_link(
        ProvenanceLink(
            link_id=f"L_PRICE_{evidence.evidence_id}",
            from_type=_PRICE_FROM_TYPE,
            from_id=f"{record.entity_code}:{record.price_date.isoformat()}",
            to_type=_PARENT_LINK_TO_TYPE,
            to_id=evidence.evidence_id,
        )
    )
    provenance_store.add_link(
        ProvenanceLink(
            link_id=f"L_EPS_{evidence.evidence_id}",
            from_type=_EPS_FROM_TYPE,
            from_id=record.source_version_id,
            to_type=_PARENT_LINK_TO_TYPE,
            to_id=evidence.evidence_id,
        )
    )


def register_historical_context_provenance_bundle(
    *,
    context_record: LatestReportedFyPerHistoricalContextRecord,
    context_evidence: EvidenceRecord,
    current_record: LatestReportedFyPerRecord,
    current_evidence: EvidenceRecord,
    historical_records: Sequence[LatestReportedFyPerRecord],
    historical_evidences: Sequence[EvidenceRecord],
    evidence_registry: EvidenceRegistry,
    provenance_store: ProvenanceStore,
) -> None:
    """Historical Valuation ContextのFull Provenance Wiring(Context→31 PER
    Parents + 各PER→Price/EPS)を1回の呼び出しで行う(Stage 3.15.3、D0092、
    要件v1 §16)。31件のWiringをOrchestration Callerが毎回手書きしなくて
    済むようにする薄いBundle Helper——大規模なGraph Frameworkは作らない
    (既存`register_latest_reported_fy_per_upstream_provenance()`/
    `verify_historical_context_provenance()`を最大限再利用する)。

    **全Validationを書き込み前に完了させる(Partial Write回避)**: `Provenance
    Store`はAppend-onlyでRollbackが無いため、書き込みを始める前に
    件数・ID対応・Entity一致・Evidence実在(`EvidenceRegistry`)を全て
    検証してから、初めてLinkの書き込みを開始する。

    検証後: (1) Context→PER Edge(31件)、(2) 各PERのPrice/EPS Edge
    (`register_latest_reported_fy_per_upstream_provenance()`を31回呼ぶ)、
    (3) 既存`verify_historical_context_provenance()`を実行して全体の
    整合性を最終確認する。
    """
    if len(historical_records) != len(historical_evidences):
        raise ValueError(
            f"historical_records({len(historical_records)}件)とhistorical_evidences"
            f"({len(historical_evidences)}件)の件数が一致しません(fail closed)"
        )
    if len(historical_records) != context_record.sample_count:
        raise ValueError(
            f"historical_recordsの件数({len(historical_records)})がcontext_record.sample_count"
            f"({context_record.sample_count})と一致しません(Historical Count Mismatch、fail closed)"
        )

    current_expected_id = latest_reported_fy_per_evidence_id_v2(current_record)
    if current_evidence.evidence_id != current_expected_id:
        raise ValueError(
            f"current_evidence.evidence_id({current_evidence.evidence_id})がcurrent_recordから導出"
            f"される期待ID({current_expected_id})と一致しません(Wrong PER Evidence ID、fail closed)"
        )
    if current_evidence.evidence_id != context_record.current_per_observation_id:
        raise ValueError(
            f"current_evidence.evidence_id({current_evidence.evidence_id})がcontext_record."
            f"current_per_observation_id({context_record.current_per_observation_id})と一致しません"
        )

    historical_expected_ids = [latest_reported_fy_per_evidence_id_v2(r) for r in historical_records]
    if len(set(historical_expected_ids)) != len(historical_expected_ids):
        duplicates = sorted({i for i in historical_expected_ids if historical_expected_ids.count(i) > 1})
        raise ValueError(
            f"historical_recordsに重複したPER Recordが含まれています(Duplicate Historical Evidence、fail closed): {duplicates}"
        )
    historical_actual_ids = [e.evidence_id for e in historical_evidences]
    if historical_expected_ids != historical_actual_ids:
        raise ValueError(
            "historical_evidencesのevidence_idが対応するhistorical_recordsから導出される期待IDと"
            f"一致しません(Wrong PER Evidence ID、fail closed): expected={historical_expected_ids} "
            f"actual={historical_actual_ids}"
        )
    if set(historical_expected_ids) != set(context_record.historical_observation_ids):
        raise ValueError(
            "historical_recordsから導出されるID集合がcontext_record.historical_observation_idsと一致しません(fail closed)"
        )

    all_pairs = [(current_record, current_evidence), *zip(historical_records, historical_evidences, strict=True)]
    for record, evidence in all_pairs:
        if record.entity_code != context_record.entity_code:
            raise ValueError(
                f"record.entity_code({record.entity_code})がcontext_record.entity_code"
                f"({context_record.entity_code})と一致しません(Wrong Entity、fail closed)"
            )
        _validate_latest_reported_fy_per_evidence(record=record, evidence=evidence)
        if evidence_registry.get(evidence.evidence_id) is None:
            raise ValueError(
                f"evidence_id={evidence.evidence_id}がEvidenceRegistryに存在しません"
                "(Fake Parent Evidence、fail closed。事前にEvidenceRegistryへ登録してください)"
            )

    for _record, evidence in all_pairs:
        provenance_store.add_link(
            ProvenanceLink(
                link_id=f"L_CTX_{evidence.evidence_id}",
                from_type=_PARENT_LINK_TO_TYPE,
                from_id=evidence.evidence_id,
                to_type=_PARENT_LINK_TO_TYPE,
                to_id=context_evidence.evidence_id,
            )
        )
    for record, evidence in all_pairs:
        register_latest_reported_fy_per_upstream_provenance(record=record, evidence=evidence, provenance_store=provenance_store)

    verify_historical_context_provenance(
        context_record,
        context_evidence_id=context_evidence.evidence_id,
        provenance_store=provenance_store,
        evidence_registry=evidence_registry,
    )


__all__ = [
    "register_historical_context_provenance_bundle",
    "register_latest_reported_fy_per_upstream_provenance",
]
