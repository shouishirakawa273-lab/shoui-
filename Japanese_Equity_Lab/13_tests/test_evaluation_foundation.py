"""`lib.evaluation`(D0107)のRegression Test(D0107 §21 Mandatory
Acceptance Tests A-L)。

`lib.evaluation.model`/`lib.evaluation.integrity`/`lib.evaluation.store`
が以下を機械的に強制することを検証する:

1. PredictionRecordはAppend-Only/Immutable——Revision(P002)作成が
   P001を一切変更しないこと。
2. ResearchSnapshot/Evidence Cutoff/Model Version/Prompt Version/
   Pipeline Versionが後から再構成可能であること。
3. EvaluationContract v2作成後もv1のEvaluationRecordが生存し続ける
   こと(Evaluation自体もAppend-Only)。
4. `evidence_cutoff`より後の`available_at`を持つEvidenceへの参照は
   `LookAheadBiasError`でFail Closedすること(PIT Reconstruction)。
5. `NO_ACTION`/`INSUFFICIENT_DATA`が明確に区別され、Predictionとは
   別Recordとして永続化されること。
6. 複数Modelの予測が同一ExperimentSpecを共有できること。
7. Tamper Evidence(Record Hash)がSerialize後の改変を検知すること。
8. 同一Entity/Target/Target Periodの複数Predictionが同じForecast
   Familyに属しつつ、個別のRecordとして残ること。
9. 異なるEntity/Target/Target Periodを持つPredictionを親として
   指定すると拒否されること。
10. 入力/取得順序の変化がRecord Identity/Hashに影響しないこと。
11. H0001には一切触れないこと。

Fixture方式は`test_thesis_impact.py`と同じ(Synthetic EDINET-shaped
ZIPを構築し、実際のD0101.1-D0103経路で実EvidenceRecordを得る)。
"""

from __future__ import annotations

import ast
import io
import zipfile
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from lib.disclosures.candidate_extraction import SemanticClaimCandidate
from lib.disclosures.evidence_integration import integrate_accepted_semantic_claim
from lib.disclosures.model import DisclosureDocument
from lib.disclosures.normalization import NormalizedDisclosureDocument, normalize_edinet_type1_zip
from lib.disclosures.semantic_claims import (
    ClaimDirection,
    EvidenceSpan,
    FaithfulnessOutcome,
    SemanticClaimType,
    build_semantic_claim,
)
from lib.errors import AppendOnlyViolationError, LookAheadBiasError
from lib.evaluation import integrity as integrity_module
from lib.evaluation import model as evaluation_model_module
from lib.evaluation import store as store_module
from lib.evaluation.integrity import compute_record_hash, verify_record_integrity
from lib.evaluation.model import (
    DecisionStatus,
    EvaluationComputationStatus,
    EvaluationFoundationSchemaError,
    EvaluationMetric,
    ForecastShape,
    ScalarForecast,
    build_decision_record,
    build_evaluation_contract,
    build_experiment_spec,
    build_prediction_record,
    build_research_snapshot,
    evaluate_scalar_absolute_error,
    forecast_family_key,
)
from lib.evaluation.store import (
    new_decision_store,
    new_evaluation_contract_store,
    new_evaluation_record_store,
    new_prediction_store,
)
from lib.evidence.model import AiDerivedProvenance, EvidenceRecord
from lib.sources.catalog import SourceAuthorityClass

_XHTML_OPEN = '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:ix="http://www.xbrl.org/2008/inlineXBRL">'
_NOW = datetime(2026, 9, 1, tzinfo=UTC)


def _htm(body_inner: str) -> bytes:
    return (f'<?xml version="1.0" encoding="UTF-8"?>{_XHTML_OPEN}<head></head><body>{body_inner}</body></html>').encode()


def _ix(name: str, inner: str) -> str:
    return f'<ix:nonNumeric name="{name}">{inner}</ix:nonNumeric>'


def _build_zip(entries: dict[str, bytes], *, date_time: tuple[int, int, int, int, int, int] = (2026, 1, 1, 0, 0, 0)) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in entries.items():
            info = zipfile.ZipInfo(filename=name, date_time=date_time)
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, content)
    return buf.getvalue()


_BODY_PATH = "XBRL/PublicDoc/0101010_honbun_test_ixbrl.htm"


def _single_member_doc(body_inner: str, *, document_id: str = "DOC1") -> NormalizedDisclosureDocument:
    raw_zip = _build_zip({_BODY_PATH: _htm(body_inner)})
    return normalize_edinet_type1_zip(document_id=document_id, raw_zip_bytes=raw_zip)


def _span_for(doc: NormalizedDisclosureDocument) -> EvidenceSpan:
    member = doc.members[0]
    return EvidenceSpan.from_text_block(document=doc, member=member, text_block=member.text_blocks[0])


def _build_evidence(
    *,
    document_id: str = "DOC1",
    text: str = "重要な変更はありません。",
    retrieved_at: datetime = datetime(2026, 8, 17, tzinfo=UTC),
) -> EvidenceRecord:
    norm_doc = _single_member_doc(_ix("jpcrp_cor:BusinessRisksTextBlock", text), document_id=document_id)
    span = _span_for(norm_doc)
    candidate = SemanticClaimCandidate(
        claim_type=SemanticClaimType.BUSINESS_RISK,
        normalized_claim_text=text,
        direction=ClaimDirection.UNSPECIFIED,
        evidence_span=span,
        extraction_version="EXTRACT_V1",
        extraction_provenance=AiDerivedProvenance(
            model_provider="test", model_name="test-model", generated_at=datetime(2026, 1, 1, tzinfo=UTC)
        ),
    )
    claim = build_semantic_claim(
        claim_type=candidate.claim_type,
        normalized_claim_text=candidate.normalized_claim_text,
        direction=candidate.direction,
        evidence_span=candidate.evidence_span,
        faithfulness_outcome=FaithfulnessOutcome.ACCEPT,
        extraction_version=candidate.extraction_version,
        schema_version=candidate.schema_version,
        extraction_provenance=candidate.extraction_provenance,
    )
    document = DisclosureDocument(
        internal_document_id=document_id,
        source_document_id="S1",
        entity_id="7203",
        title="半期報告書",
        originating_source="EDINET",
        delivery_provider="EDINET",
        retrieved_at=retrieved_at,
    )
    result = integrate_accepted_semantic_claim(
        claim=claim, document=document, source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL
    )
    assert result.evidence is not None
    return result.evidence


def _snapshot(snapshot_id: str = "SNAP1", evidence_records: tuple[EvidenceRecord, ...] = ()):
    return build_research_snapshot(
        snapshot_id=snapshot_id,
        entity_id="7203",
        evidence_cutoff=datetime(2026, 8, 20, tzinfo=UTC),
        research_artifact_id="ART1",
        research_artifact_version=1,
        created_at=_NOW,
        evidence_records=evidence_records,
        evidence_ids=tuple(e.evidence_id for e in evidence_records),
    )


def _prediction(
    *,
    prediction_id: str,
    value: str = "320",
    parent_prediction_id: str | None = None,
    existing_predictions: tuple = (),
    entity_id: str = "7203",
    target: str = "EPS",
    target_period: str = "FY2027",
    research_snapshot_id: str = "SNAP1",
    prompt_version: str | None = "PROMPT_V1",
):
    return build_prediction_record(
        prediction_id=prediction_id,
        entity_id=entity_id,
        target=target,
        target_period=target_period,
        forecast_shape=ForecastShape.SCALAR,
        scalar_forecast=ScalarForecast(value=Decimal(value), unit="JPY"),
        created_at=_NOW,
        evidence_cutoff=datetime(2026, 8, 20, tzinfo=UTC),
        research_snapshot_id=research_snapshot_id,
        model_version="MODEL_V1",
        research_pipeline_version="PIPELINE_V1",
        prompt_version=prompt_version,
        parent_prediction_id=parent_prediction_id,
        existing_predictions=existing_predictions,
    )


# --- TEST A: Revision never mutates parent ----------------------------------


def test_a_revision_never_mutates_parent() -> None:
    p001 = _prediction(prediction_id="P001", value="320")
    original_hash = p001.record_hash
    original_fields = {k: v for k, v in vars(p001).items()}

    p002 = _prediction(prediction_id="P002", value="290", parent_prediction_id="P001", existing_predictions=(p001,))

    assert p001.record_hash == original_hash
    assert {k: v for k, v in vars(p001).items()} == original_fields
    assert p002.parent_prediction_id == "P001"
    assert p002.record_hash != p001.record_hash
    assert verify_record_integrity(p001)
    assert verify_record_integrity(p002)


# --- TEST B: Retrieve P001, reconstruct context ------------------------------


def test_b_prediction_context_is_reconstructable() -> None:
    evidence = _build_evidence()
    snapshot = _snapshot(evidence_records=(evidence,))
    p001 = _prediction(prediction_id="P001", research_snapshot_id=snapshot.snapshot_id)

    assert p001.research_snapshot_id == snapshot.snapshot_id
    assert p001.evidence_cutoff == snapshot.evidence_cutoff
    assert p001.model_version == "MODEL_V1"
    assert p001.prompt_version == "PROMPT_V1"
    assert p001.research_pipeline_version == "PIPELINE_V1"
    assert snapshot.evidence_ids == (evidence.evidence_id,)


# --- TEST C: Evaluation v1 survives v2 ---------------------------------------


def test_c_evaluation_v1_survives_v2() -> None:
    p001 = _prediction(prediction_id="P001", value="320")
    contract_v1 = build_evaluation_contract(
        evaluation_contract_id="EC1",
        evaluation_contract_version=1,
        target="EPS",
        target_period="FY2027",
        actual_truth_description="final sanctioned FY2027 EPS actual",
        metric=EvaluationMetric.ABSOLUTE_ERROR,
        evaluable_at_policy="after FY2027 annual report finalized",
        created_at=_NOW,
    )
    result_v1 = evaluate_scalar_absolute_error(
        evaluation_id="E001",
        prediction=p001,
        contract=contract_v1,
        actual_value=Decimal("300"),
        actual_reference="FY2027_ACTUAL_EPS",
        evaluated_at=_NOW,
    )
    assert result_v1.status == EvaluationComputationStatus.COMPUTED
    e001 = result_v1.evaluation
    assert e001 is not None

    contract_v2 = build_evaluation_contract(
        evaluation_contract_id="EC1",
        evaluation_contract_version=2,
        target="EPS",
        target_period="FY2027",
        actual_truth_description="final sanctioned FY2027 EPS actual (restated)",
        metric=EvaluationMetric.ABSOLUTE_ERROR,
        evaluable_at_policy="after FY2027 annual report finalized and restated",
        created_at=_NOW,
    )
    result_v2 = evaluate_scalar_absolute_error(
        evaluation_id="E002",
        prediction=p001,
        contract=contract_v2,
        actual_value=Decimal("305"),
        actual_reference="FY2027_ACTUAL_EPS_RESTATED",
        evaluated_at=_NOW,
    )
    e002 = result_v2.evaluation
    assert e002 is not None

    # v1 survives unchanged
    assert verify_record_integrity(e001)
    assert e001.result_value == Decimal("20")
    assert e002.result_value == Decimal("15")
    assert e001.evaluation_id != e002.evaluation_id


# --- TEST D: Future Evidence rejected -----------------------------------------


def test_d_future_evidence_rejected() -> None:
    evidence_cutoff = datetime(2026, 8, 1, tzinfo=UTC)
    future_evidence = _build_evidence(retrieved_at=datetime(2026, 9, 1, tzinfo=UTC))  # available_at > cutoff

    with pytest.raises(LookAheadBiasError):
        build_research_snapshot(
            snapshot_id="SNAP_FUTURE",
            entity_id="7203",
            evidence_cutoff=evidence_cutoff,
            research_artifact_id="ART1",
            research_artifact_version=1,
            created_at=_NOW,
            evidence_records=(future_evidence,),
            evidence_ids=(future_evidence.evidence_id,),
        )


# --- TEST E: NO_ACTION vs INSUFFICIENT_DATA ----------------------------------


def test_e_no_action_and_insufficient_data_are_distinct_and_separate_from_prediction() -> None:
    p001 = _prediction(prediction_id="P001")
    no_action = build_decision_record(
        decision_id="D_NA",
        created_at=_NOW,
        entity_id="7203",
        research_snapshot_id="SNAP1",
        decision_status=DecisionStatus.NO_ACTION,
        decision_policy_version="POLICY_V1",
        prediction_ids=(p001.prediction_id,),
    )
    insufficient = build_decision_record(
        decision_id="D_ID",
        created_at=_NOW,
        entity_id="7203",
        research_snapshot_id="SNAP1",
        decision_status=DecisionStatus.INSUFFICIENT_DATA,
        decision_policy_version="POLICY_V1",
    )

    assert no_action.decision_status != insufficient.decision_status
    assert no_action.decision_status == DecisionStatus.NO_ACTION
    assert insufficient.decision_status == DecisionStatus.INSUFFICIENT_DATA
    # DecisionRecordはPredictionRecordと別型であり、Fieldとして混在しない
    assert not hasattr(p001, "decision_status")


# --- TEST F: Shared ExperimentSpec -------------------------------------------


def test_f_multiple_models_share_identical_experiment_conditions() -> None:
    spec = build_experiment_spec(
        experiment_id="EXP1",
        universe_definition_id="UNIVERSE_TOPIX500_V1",
        information_cutoff_policy="T-1 close",
        benchmark_definition_id="TOPIX",
        execution_policy_reference="EXEC_POLICY_V1",
        transaction_cost_policy_reference="TXCOST_POLICY_V1",
        earliest_executable_time_policy_reference="T+1 open",
        liquidity_eligibility_policy_reference="LIQUIDITY_POLICY_V1",
        corporate_action_handling_version="CA_V1",
        created_at=_NOW,
        variant_ids=("MODEL_A", "MODEL_B"),
    )
    pred_a = _prediction(prediction_id="P_A", existing_predictions=())
    pred_b = build_prediction_record(
        prediction_id="P_B",
        entity_id="7203",
        target="EPS",
        target_period="FY2027",
        forecast_shape=ForecastShape.SCALAR,
        scalar_forecast=ScalarForecast(value=Decimal("310"), unit="JPY"),
        created_at=_NOW,
        evidence_cutoff=datetime(2026, 8, 20, tzinfo=UTC),
        research_snapshot_id="SNAP1",
        model_version="MODEL_V2",
        research_pipeline_version="PIPELINE_V1",
    )

    assert pred_a.model_version != pred_b.model_version
    assert "MODEL_A" in spec.variant_ids and "MODEL_B" in spec.variant_ids
    reloaded_spec = replace(spec)
    assert reloaded_spec == spec
    assert verify_record_integrity(spec)


# --- TEST G: Scalar evaluation reproducible ----------------------------------


def test_g_scalar_evaluation_is_deterministically_reproducible() -> None:
    p001 = _prediction(prediction_id="P001", value="320")
    contract = build_evaluation_contract(
        evaluation_contract_id="EC_G",
        evaluation_contract_version=1,
        target="EPS",
        target_period="FY2027",
        actual_truth_description="final sanctioned FY2027 EPS actual",
        metric=EvaluationMetric.ABSOLUTE_ERROR,
        evaluable_at_policy="after FY2027 annual report finalized",
        created_at=_NOW,
    )
    result_1 = evaluate_scalar_absolute_error(
        evaluation_id="E_G1",
        prediction=p001,
        contract=contract,
        actual_value=Decimal("300"),
        actual_reference="ACTUAL",
        evaluated_at=_NOW,
    )
    result_2 = evaluate_scalar_absolute_error(
        evaluation_id="E_G1",
        prediction=p001,
        contract=contract,
        actual_value=Decimal("300"),
        actual_reference="ACTUAL",
        evaluated_at=_NOW,
    )
    assert result_1.evaluation is not None
    assert result_2.evaluation is not None
    assert result_1.evaluation.result_value == result_2.evaluation.result_value == Decimal("20")
    assert result_1.evaluation.record_hash == result_2.evaluation.record_hash


# --- TEST H: Tamper detection -------------------------------------------------


def test_h_mutated_serialized_prediction_fails_integrity_verification(tmp_path: Path) -> None:
    p001 = _prediction(prediction_id="P001", value="320")
    assert verify_record_integrity(p001)

    store = new_prediction_store(tmp_path / "predictions.jsonl")
    store.record(p001)

    raw_lines = (tmp_path / "predictions.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(raw_lines) == 1
    import json

    tampered_dict = json.loads(raw_lines[0])
    tampered_dict["scalar_forecast"]["value"] = "999999"
    (tmp_path / "predictions.jsonl").write_text(json.dumps(tampered_dict, ensure_ascii=False) + "\n", encoding="utf-8")

    from lib.evaluation.store import _prediction_from_dict

    reloaded_tampered = _prediction_from_dict(tampered_dict)
    assert not verify_record_integrity(reloaded_tampered)


# --- TEST I: Forecast Family grouping -----------------------------------------


def test_i_same_family_but_three_distinct_records() -> None:
    p001 = _prediction(prediction_id="P001", value="320")
    p002 = _prediction(prediction_id="P002", value="290", parent_prediction_id="P001", existing_predictions=(p001,))
    p003 = _prediction(prediction_id="P003", value="300", parent_prediction_id="P002", existing_predictions=(p001, p002))

    assert forecast_family_key(p001) == forecast_family_key(p002) == forecast_family_key(p003) == ("7203", "EPS", "FY2027")
    assert {p001.prediction_id, p002.prediction_id, p003.prediction_id} == {"P001", "P002", "P003"}
    assert len({p001.record_hash, p002.record_hash, p003.record_hash}) == 3


# --- TEST J: Parent mismatch rejected -----------------------------------------


def test_j_parent_with_different_entity_is_rejected() -> None:
    p001 = _prediction(prediction_id="P001", entity_id="7203")
    with pytest.raises(EvaluationFoundationSchemaError):
        _prediction(prediction_id="P002", entity_id="9999", parent_prediction_id="P001", existing_predictions=(p001,))


def test_j_parent_with_different_target_is_rejected() -> None:
    p001 = _prediction(prediction_id="P001", target="EPS")
    with pytest.raises(EvaluationFoundationSchemaError):
        _prediction(prediction_id="P002", target="REVENUE", parent_prediction_id="P001", existing_predictions=(p001,))


def test_j_parent_with_different_target_period_is_rejected() -> None:
    p001 = _prediction(prediction_id="P001", target_period="FY2027")
    with pytest.raises(EvaluationFoundationSchemaError):
        _prediction(prediction_id="P002", target_period="FY2028", parent_prediction_id="P001", existing_predictions=(p001,))


def test_j_missing_parent_is_rejected() -> None:
    with pytest.raises(EvaluationFoundationSchemaError):
        _prediction(prediction_id="P002", parent_prediction_id="P001_DOES_NOT_EXIST", existing_predictions=())


def test_j_cycle_is_rejected() -> None:
    p001 = _prediction(prediction_id="P001")
    p002 = _prediction(prediction_id="P002", parent_prediction_id="P001", existing_predictions=(p001,))
    # P001自身がP002を親として指すよう不正に構築されたPoolを模擬する(循環)。
    p001_corrupted = replace(p001, parent_prediction_id="P002")
    with pytest.raises(EvaluationFoundationSchemaError):
        _prediction(prediction_id="P003", parent_prediction_id="P001", existing_predictions=(p001_corrupted, p002))


# --- TEST K: Ordering independence --------------------------------------------


def test_k_hash_unaffected_by_evidence_id_ordering() -> None:
    e1 = _build_evidence(document_id="DOC1", text="Order1。")
    e2 = _build_evidence(document_id="DOC2", text="Order2。")

    snap_a = build_research_snapshot(
        snapshot_id="SNAP_A",
        entity_id="7203",
        evidence_cutoff=datetime(2026, 8, 20, tzinfo=UTC),
        research_artifact_id="ART1",
        research_artifact_version=1,
        created_at=_NOW,
        evidence_records=(e1, e2),
        evidence_ids=(e1.evidence_id, e2.evidence_id),
    )
    snap_b = build_research_snapshot(
        snapshot_id="SNAP_A",
        entity_id="7203",
        evidence_cutoff=datetime(2026, 8, 20, tzinfo=UTC),
        research_artifact_id="ART1",
        research_artifact_version=1,
        created_at=_NOW,
        evidence_records=(e2, e1),
        evidence_ids=(e2.evidence_id, e1.evidence_id),
    )

    assert snap_a.record_hash == snap_b.record_hash
    assert snap_a.evidence_ids == snap_b.evidence_ids


def test_k_hash_unaffected_by_prediction_id_tuple_ordering() -> None:
    decision_a = build_decision_record(
        decision_id="D1",
        created_at=_NOW,
        entity_id="7203",
        research_snapshot_id="SNAP1",
        decision_status=DecisionStatus.ACTION,
        decision_policy_version="V1",
        prediction_ids=("P001", "P002"),
    )
    decision_b = build_decision_record(
        decision_id="D1",
        created_at=_NOW,
        entity_id="7203",
        research_snapshot_id="SNAP1",
        decision_status=DecisionStatus.ACTION,
        decision_policy_version="V1",
        prediction_ids=("P002", "P001"),
    )
    assert decision_a.record_hash == decision_b.record_hash
    assert decision_a.prediction_ids == decision_b.prediction_ids


def test_k_store_retrieval_order_independent(tmp_path: Path) -> None:
    p1 = _prediction(prediction_id="P001")
    p2 = build_prediction_record(
        prediction_id="P002",
        entity_id="7203",
        target="REVENUE",
        target_period="FY2027",
        forecast_shape=ForecastShape.SCALAR,
        scalar_forecast=ScalarForecast(value=Decimal("1000"), unit="JPY"),
        created_at=_NOW,
        evidence_cutoff=datetime(2026, 8, 20, tzinfo=UTC),
        research_snapshot_id="SNAP1",
        model_version="MODEL_V1",
        research_pipeline_version="PIPELINE_V1",
    )
    store = new_prediction_store(tmp_path / "predictions.jsonl")
    store.record(p1)
    store.record(p2)
    all_records = store.all()
    assert {r.prediction_id for r in all_records} == {"P001", "P002"}
    assert store.get("P001") == p1
    assert store.get("P002") == p2


# --- TEST L: H0001 untouched --------------------------------------------------


def test_l_h0001_not_referenced_by_evaluation_module() -> None:
    for module_path in (
        evaluation_model_module.__file__,
        integrity_module.__file__,
        store_module.__file__,
    ):
        source = Path(module_path).read_text(encoding="utf-8")
        assert "H0001" not in source
        assert "locked_test" not in source.lower()


# ============================================================
# Store: Duplicate ID Rejection (D0107 §20)
# ============================================================


def test_store_rejects_duplicate_id_even_with_identical_content(tmp_path: Path) -> None:
    p001 = _prediction(prediction_id="P001")
    store = new_prediction_store(tmp_path / "predictions.jsonl")
    store.record(p001)
    with pytest.raises(AppendOnlyViolationError):
        store.record(p001)


def test_store_rejects_duplicate_id_with_different_content(tmp_path: Path) -> None:
    p001_v1 = _prediction(prediction_id="P001", value="320")
    p001_v2 = _prediction(prediction_id="P001", value="999")
    store = new_prediction_store(tmp_path / "predictions.jsonl")
    store.record(p001_v1)
    with pytest.raises(AppendOnlyViolationError):
        store.record(p001_v2)


def test_build_prediction_record_rejects_prediction_id_collision_in_existing_predictions_pool() -> None:
    """Regression(/code-review high指摘, D0107): `existing_predictions`
    Poolに既に同じ`prediction_id`を持つRecordがある場合、`parent_
    prediction_id`の指定有無を問わず拒否する——拒否しなければ、同一
    `prediction_id`でも異なるContent(異なる`scalar_forecast`/
    `record_hash`)を持つ2つのIn-Memory Instanceが共存してしまい、
    AppendOnlyRecordStoreへ永続化する前の段階でSilent ID Collisionが
    成立してしまう(forbidden_actions「no silent overwrite of an
    existing PredictionRecord」に反する)。"""
    p001 = _prediction(prediction_id="P001", value="320")

    with pytest.raises(EvaluationFoundationSchemaError):
        _prediction(prediction_id="P001", value="999", existing_predictions=(p001,))


def test_build_prediction_record_rejects_prediction_id_collision_even_without_parent() -> None:
    p001 = _prediction(prediction_id="P001", value="320")

    with pytest.raises(EvaluationFoundationSchemaError):
        build_prediction_record(
            prediction_id="P001",
            entity_id="9999",
            target="REVENUE",
            target_period="FY2099",
            forecast_shape=ForecastShape.SCALAR,
            scalar_forecast=ScalarForecast(value=Decimal("1"), unit="JPY"),
            created_at=_NOW,
            evidence_cutoff=datetime(2026, 8, 20, tzinfo=UTC),
            research_snapshot_id="SNAP_OTHER",
            model_version="MODEL_OTHER",
            research_pipeline_version="PIPELINE_OTHER",
            existing_predictions=(p001,),
        )


def test_evaluation_contract_store_preserves_both_versions_under_same_id(tmp_path: Path) -> None:
    """Regression(/code-review high指摘, D0107): EvaluationContractは
    `evaluation_contract_id`が同一でもVersionが異なれば共存しなければ
    ならない(D0107 §C/§18の中心的要件そのもの)。`new_evaluation_
    contract_store()`のIdentityが`evaluation_contract_id`単独だと、
    v1記録後にv2を記録しようとした際`AppendOnlyViolationError`に
    なってしまい、Versioningという本Recordの存在意義と矛盾する。"""
    contract_v1 = build_evaluation_contract(
        evaluation_contract_id="EC1",
        evaluation_contract_version=1,
        target="EPS",
        target_period="FY2027",
        actual_truth_description="actual",
        metric=EvaluationMetric.ABSOLUTE_ERROR,
        evaluable_at_policy="policy v1",
        created_at=_NOW,
    )
    contract_v2 = build_evaluation_contract(
        evaluation_contract_id="EC1",
        evaluation_contract_version=2,
        target="EPS",
        target_period="FY2027",
        actual_truth_description="actual restated",
        metric=EvaluationMetric.ABSOLUTE_ERROR,
        evaluable_at_policy="policy v2",
        created_at=_NOW,
    )
    store = new_evaluation_contract_store(tmp_path / "contracts.jsonl")
    store.record(contract_v1)
    store.record(contract_v2)

    all_records = store.all()
    assert len(all_records) == 2
    assert {r.evaluation_contract_version for r in all_records} == {1, 2}
    # 同一(id, version)の再記録は依然Rejectされる(重複ID Policyは健在)。
    with pytest.raises(AppendOnlyViolationError):
        store.record(contract_v1)


def test_decision_store_persists_separately_from_prediction_store(tmp_path: Path) -> None:
    p001 = _prediction(prediction_id="P001")
    decision = build_decision_record(
        decision_id="D1",
        created_at=_NOW,
        entity_id="7203",
        research_snapshot_id="SNAP1",
        decision_status=DecisionStatus.ACTION,
        decision_policy_version="V1",
        prediction_ids=(p001.prediction_id,),
    )
    pred_store = new_prediction_store(tmp_path / "predictions.jsonl")
    decision_store = new_decision_store(tmp_path / "decisions.jsonl")
    pred_store.record(p001)
    decision_store.record(decision)

    assert pred_store.get("D1") is None
    assert decision_store.get("P001") is None
    assert pred_store.get("P001") == p001
    assert decision_store.get("D1") == decision


def test_evaluation_record_store_preserves_both_versions(tmp_path: Path) -> None:
    p001 = _prediction(prediction_id="P001")
    contract_v1 = build_evaluation_contract(
        evaluation_contract_id="EC1",
        evaluation_contract_version=1,
        target="EPS",
        target_period="FY2027",
        actual_truth_description="actual",
        metric=EvaluationMetric.ABSOLUTE_ERROR,
        evaluable_at_policy="policy",
        created_at=_NOW,
    )
    contract_v2 = build_evaluation_contract(
        evaluation_contract_id="EC1",
        evaluation_contract_version=2,
        target="EPS",
        target_period="FY2027",
        actual_truth_description="actual restated",
        metric=EvaluationMetric.ABSOLUTE_ERROR,
        evaluable_at_policy="policy v2",
        created_at=_NOW,
    )
    r1 = evaluate_scalar_absolute_error(
        evaluation_id="E1",
        prediction=p001,
        contract=contract_v1,
        actual_value=Decimal("300"),
        actual_reference="A",
        evaluated_at=_NOW,
    )
    r2 = evaluate_scalar_absolute_error(
        evaluation_id="E2",
        prediction=p001,
        contract=contract_v2,
        actual_value=Decimal("305"),
        actual_reference="A2",
        evaluated_at=_NOW,
    )
    assert r1.evaluation is not None
    assert r2.evaluation is not None

    store = new_evaluation_record_store(tmp_path / "evaluations.jsonl")
    store.record(r1.evaluation)
    store.record(r2.evaluation)

    assert len(store.all()) == 2
    assert store.get("E1") is not None
    assert store.get("E2") is not None


# ============================================================
# Evaluation Category Mismatch (D0107 §29 Reviewer Focus #10)
# ============================================================


def test_evaluation_target_mismatch_fails_closed() -> None:
    p001 = _prediction(prediction_id="P001", target="EPS")
    wrong_contract = build_evaluation_contract(
        evaluation_contract_id="EC_WRONG",
        evaluation_contract_version=1,
        target="REVENUE",
        target_period="FY2027",
        actual_truth_description="actual revenue",
        metric=EvaluationMetric.ABSOLUTE_ERROR,
        evaluable_at_policy="policy",
        created_at=_NOW,
    )
    result = evaluate_scalar_absolute_error(
        evaluation_id="E_WRONG",
        prediction=p001,
        contract=wrong_contract,
        actual_value=Decimal("1000"),
        actual_reference="A",
        evaluated_at=_NOW,
    )
    assert result.status == EvaluationComputationStatus.TARGET_MISMATCH
    assert result.evaluation is None


def test_evaluation_shape_mismatch_fails_closed() -> None:
    bull_base_bear_pred = build_prediction_record(
        prediction_id="P_BBB",
        entity_id="7203",
        target="EPS",
        target_period="FY2027",
        forecast_shape=ForecastShape.BULL_BASE_BEAR,
        bull_base_bear_forecast=__import__("lib.evaluation.model", fromlist=["BullBaseBearForecast"]).BullBaseBearForecast(
            bull=Decimal("350"), base=Decimal("320"), bear=Decimal("280"), unit="JPY"
        ),
        created_at=_NOW,
        evidence_cutoff=datetime(2026, 8, 20, tzinfo=UTC),
        research_snapshot_id="SNAP1",
        model_version="MODEL_V1",
        research_pipeline_version="PIPELINE_V1",
    )
    contract = build_evaluation_contract(
        evaluation_contract_id="EC1",
        evaluation_contract_version=1,
        target="EPS",
        target_period="FY2027",
        actual_truth_description="actual",
        metric=EvaluationMetric.ABSOLUTE_ERROR,
        evaluable_at_policy="policy",
        created_at=_NOW,
    )
    result = evaluate_scalar_absolute_error(
        evaluation_id="E_SHAPE",
        prediction=bull_base_bear_pred,
        contract=contract,
        actual_value=Decimal("300"),
        actual_reference="A",
        evaluated_at=_NOW,
    )
    assert result.status == EvaluationComputationStatus.SHAPE_MISMATCH


# ============================================================
# Tamper Evidence on EvaluationContract / ExperimentSpec (D0107 §18)
# ============================================================


def test_evaluation_contract_integrity_detects_tamper() -> None:
    contract = build_evaluation_contract(
        evaluation_contract_id="EC1",
        evaluation_contract_version=1,
        target="EPS",
        target_period="FY2027",
        actual_truth_description="actual",
        metric=EvaluationMetric.ABSOLUTE_ERROR,
        evaluable_at_policy="policy",
        created_at=_NOW,
    )
    assert verify_record_integrity(contract)
    tampered = replace(contract, target="REVENUE")
    assert not verify_record_integrity(tampered)


def test_experiment_spec_integrity_detects_tamper() -> None:
    spec = build_experiment_spec(
        experiment_id="EXP1",
        universe_definition_id="U1",
        information_cutoff_policy="P1",
        benchmark_definition_id="TOPIX",
        execution_policy_reference="E1",
        transaction_cost_policy_reference="T1",
        earliest_executable_time_policy_reference="EX1",
        liquidity_eligibility_policy_reference="L1",
        corporate_action_handling_version="CA1",
        created_at=_NOW,
    )
    assert verify_record_integrity(spec)
    tampered = replace(spec, benchmark_definition_id="CASH")
    assert not verify_record_integrity(tampered)


def test_decision_record_hash_excludes_itself() -> None:
    decision = build_decision_record(
        decision_id="D1",
        created_at=_NOW,
        entity_id="7203",
        research_snapshot_id="SNAP1",
        decision_status=DecisionStatus.WATCH,
        decision_policy_version="V1",
    )
    payload = {k: v for k, v in vars(decision).items() if k != "record_hash"}
    recomputed = compute_record_hash(payload)
    assert recomputed == decision.record_hash


# ============================================================
# No LLM / No Backtest / No Valuation / No Portfolio Logic (Source Level)
# ============================================================


def test_evaluation_modules_have_no_model_dependency() -> None:
    for module_path in (evaluation_model_module.__file__, integrity_module.__file__, store_module.__file__):
        source = Path(module_path).read_text(encoding="utf-8")
        for forbidden in ("import openai", "import anthropic", "requests.post", "httpx.", ".classify(", ".extract("):
            assert forbidden not in source


def test_evaluation_modules_have_no_valuation_backtest_or_portfolio_logic() -> None:
    source = Path(evaluation_model_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    identifiers: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            identifiers.add(node.id)
        elif isinstance(node, ast.Attribute):
            identifiers.add(node.attr)
        elif isinstance(node, ast.arg):
            identifiers.add(node.arg)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            identifiers.add(node.name)
        elif isinstance(node, ast.alias):
            identifiers.add(node.name)
            if node.asname:
                identifiers.add(node.asname)
    # Identifier単位の完全一致でCheckする(Substring Matchだと
    # `EvaluationContract`等の正当な識別子が`valuation`に誤反応する)。
    for forbidden in (
        "BUY",
        "SELL",
        "expected_return",
        "fair_value",
        "intrinsic_value",
        "Backtest",
        "PortfolioOptimizer",
        "PositionSizing",
        "Correlation",
        "Sharpe",
    ):
        assert forbidden not in identifiers
