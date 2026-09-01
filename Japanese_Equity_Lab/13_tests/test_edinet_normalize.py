"""Phase4B-2(D0046追記): `lib.disclosures.providers.edinet_normalize`のテスト。

2026-08-17のLocal Real Data Validation結果(実Field名・実lifecycle値・
実null出現パターン)を反映する。外部呼び出しは一切行わない。
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from lib.disclosures.model import DocumentKind
from lib.disclosures.providers.edinet_normalize import (
    EdinetDisclosureStatus,
    EdinetDocInfoEditStatus,
    EdinetLegalStatus,
    EdinetWithdrawalStatus,
    parse_edinet_documents_list_payload,
)
from lib.errors import DataSourceError
from lib.evidence.model import AvailabilityBasis

_RETRIEVED_AT = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)


def _body(results: list[dict[str, object]]) -> dict[str, object]:
    return {"metadata": {"status": "200", "resultset": {"count": len(results)}}, "results": results}


# --- Top-level payload gate(Adapter層とは独立の防御的検証) ---


def test_parse_rejects_non_200_metadata_status() -> None:
    with pytest.raises(DataSourceError, match="200"):
        parse_edinet_documents_list_payload({"metadata": {"status": "401"}, "results": []}, retrieved_at=_RETRIEVED_AT)


def test_parse_rejects_missing_results() -> None:
    with pytest.raises(DataSourceError, match="results"):
        parse_edinet_documents_list_payload({"metadata": {"status": "200"}}, retrieved_at=_RETRIEVED_AT)


def test_parse_skips_non_dict_rows_without_raising() -> None:
    parsed = parse_edinet_documents_list_payload(_body(["not-a-dict"]), retrieved_at=_RETRIEVED_AT)
    assert parsed == []


# --- "0"/"1" Flag Parsing(bool("0")==True 罠の回帰) ---


def test_flag_parsing_explicit_zero_one_not_python_truthiness() -> None:
    row = {"docID": "D1", "xbrlFlag": "0", "pdfFlag": "1"}
    (_doc, meta) = parse_edinet_documents_list_payload(_body([row]), retrieved_at=_RETRIEVED_AT)[0]
    # bool("0") == True という罠が残っていれば has_xbrl は誤って True になる。
    assert meta.has_xbrl is False
    assert meta.has_pdf is True


def test_flag_parsing_missing_flag_is_none_not_false() -> None:
    row = {"docID": "D1"}
    (_doc, meta) = parse_edinet_documents_list_payload(_body([row]), retrieved_at=_RETRIEVED_AT)[0]
    assert meta.has_xbrl is None
    assert meta.has_pdf is None
    assert meta.has_attachments is None
    assert meta.has_english_docs is None
    assert meta.has_csv is None


def test_flag_parsing_unknown_string_value_fails_closed_to_none() -> None:
    row = {"docID": "D1", "csvFlag": "maybe"}
    (_doc, meta) = parse_edinet_documents_list_payload(_body([row]), retrieved_at=_RETRIEVED_AT)[0]
    assert meta.has_csv is None


# --- Lifecycle Multi-state(Booleanへ落とさない、未知値fail closed、null保持) ---


def test_lifecycle_status_values_are_typed_enum_members_not_bool() -> None:
    row = {
        "docID": "D1",
        "withdrawalStatus": "1",
        "docInfoEditStatus": "2",
        "disclosureStatus": "3",
        "legalStatus": "1",
    }
    (_doc, meta) = parse_edinet_documents_list_payload(_body([row]), retrieved_at=_RETRIEVED_AT)[0]
    assert meta.withdrawal_status is EdinetWithdrawalStatus.WITHDRAWAL_NOTICE
    assert meta.doc_info_edit_status is EdinetDocInfoEditStatus.EDITED_DOCUMENT
    assert meta.disclosure_status is EdinetDisclosureStatus.NON_DISCLOSURE_LIFTED
    assert meta.legal_status is EdinetLegalStatus.UNDER_PUBLIC_VIEWING
    assert not isinstance(meta.withdrawal_status, bool)


def test_lifecycle_status_zero_is_other_not_falsy_none() -> None:
    """ "0"("その他")は明示的なEnumメンバーであり、Noneとは区別される
    (bool/truthiness的な「0=無し」扱いをしない)。"""
    row = {"docID": "D1", "withdrawalStatus": "0"}
    (_doc, meta) = parse_edinet_documents_list_payload(_body([row]), retrieved_at=_RETRIEVED_AT)[0]
    assert meta.withdrawal_status is EdinetWithdrawalStatus.OTHER
    assert meta.withdrawal_status is not None


def test_lifecycle_status_unknown_value_fails_closed_to_unknown_member() -> None:
    row = {"docID": "D1", "legalStatus": "99"}
    (_doc, meta) = parse_edinet_documents_list_payload(_body([row]), retrieved_at=_RETRIEVED_AT)[0]
    assert meta.legal_status is EdinetLegalStatus.UNKNOWN


def test_lifecycle_status_missing_field_is_none_distinct_from_unknown_member() -> None:
    """Fieldが欠損/nullの場合はNone(「値が無い」)であり、
    UNKNOWN(「値はあるが認識できない」)とは意味が異なる(D0046 §13)。"""
    row = {"docID": "D1"}
    (_doc, meta) = parse_edinet_documents_list_payload(_body([row]), retrieved_at=_RETRIEVED_AT)[0]
    assert meta.legal_status is None
    assert meta.withdrawal_status is None


# --- Null Semantics(縦覧期間満了・取下げ後にField自体がnullになるケース) ---


def test_null_record_fields_preserved_as_none_not_coerced() -> None:
    """docIDだけ存在し、他の多くのFieldがnullになったRecord(縦覧期間満了後の
    実観測パターン、D0046 §13)を、0/False/UNKNOWN entityへ勝手に変換しない
    ことを確認する。"""
    row = {
        "docID": "D1",
        "edinetCode": None,
        "secCode": None,
        "submitDateTime": None,
        "docDescription": None,
    }
    (doc, meta) = parse_edinet_documents_list_payload(_body([row]), retrieved_at=_RETRIEVED_AT)[0]
    assert meta.filer_edinet_code is None
    assert meta.filer_sec_code is None
    assert meta.submitted_at is None
    # docDescriptionがnullでも、Common Coreのtitleは空文字列ではなく明示的な
    # Placeholderになる(必須Fieldを無言で空欄にしない)。
    assert doc.title != ""
    assert "D1" in doc.title


# --- secCode / Role-aware Entity(filer != issuer != subject、Local実データ確認) ---


def test_sec_code_preserved_as_raw_five_character_filer_identifier() -> None:
    """Local実データ確認: 7203(Toyota)のsecCode="72030"(5桁)。J-Quantsの
    5桁ゼロパディング規約と同じ見た目でも、EDINET Adapterが独自にPaddingを
    追加/削除する処理はしない(Raw値をそのまま保持する)。"""
    row = {"docID": "D1", "secCode": "72030"}
    (_doc, meta) = parse_edinet_documents_list_payload(_body([row]), retrieved_at=_RETRIEVED_AT)[0]
    assert meta.filer_sec_code == "72030"
    assert len(meta.filer_sec_code) == 5


def test_sec_code_is_filer_identifier_not_automatically_entity_id() -> None:
    """`DisclosureDocument.entity_id`はsecCodeから機械的に決定しない
    (D0046 §12 — Role-aware Entity Mappingは未実装、EntityRegistry統合は
    将来Phase)。"""
    row = {"docID": "D1", "secCode": "72030", "edinetCode": "E00001"}
    (doc, _meta) = parse_edinet_documents_list_payload(_body([row]), retrieved_at=_RETRIEVED_AT)[0]
    assert doc.entity_id is None


def test_filer_issuer_subject_roles_preserved_separately() -> None:
    """Local実データ確認: 大量保有報告書ではfiler(提出者) != issuer(発行会社)。
    3つのRoleを単一Fieldへ混同しない。"""
    row = {
        "docID": "D1",
        "edinetCode": "E_FILER",
        "issuerEdinetCode": "E_ISSUER",
        "subjectEdinetCode": "E_SUBJECT",
        "subsidiaryEdinetCode": "E_SUBSIDIARY",
    }
    (_doc, meta) = parse_edinet_documents_list_payload(_body([row]), retrieved_at=_RETRIEVED_AT)[0]
    assert meta.filer_edinet_code == "E_FILER"
    assert meta.issuer_edinet_code == "E_ISSUER"
    assert meta.subject_edinet_code == "E_SUBJECT"
    assert meta.subsidiary_edinet_code == "E_SUBSIDIARY"
    # 4つとも異なる値であり、いずれか1つへ暗黙に統合されていない。
    assert len({meta.filer_edinet_code, meta.issuer_edinet_code, meta.subject_edinet_code, meta.subsidiary_edinet_code}) == 4


# --- Timestamp Semantics(submitDateTime/opeDateTime/processDateTime) ---


def test_submit_datetime_not_automatically_market_public_at() -> None:
    row = {"docID": "D1", "submitDateTime": "2024-05-08 15:30"}
    (doc, meta) = parse_edinet_documents_list_payload(_body([row]), retrieved_at=_RETRIEVED_AT)[0]
    assert meta.submitted_at is not None  # EDINET固有のsubmitted_atとしては保持する
    assert doc.market_public_at is None  # Common Coreのmarket_public_atへは反映しない
    assert doc.market_public_at_basis == AvailabilityBasis.UNKNOWN


def test_submit_datetime_not_automatically_provider_available_at() -> None:
    row = {"docID": "D1", "submitDateTime": "2024-05-08 15:30"}
    (doc, _meta) = parse_edinet_documents_list_payload(_body([row]), retrieved_at=_RETRIEVED_AT)[0]
    assert doc.provider_available_at is None
    assert doc.provider_available_at_basis == AvailabilityBasis.UNKNOWN


def test_submitted_at_parsed_as_jst() -> None:
    row = {"docID": "D1", "submitDateTime": "2024-05-08 15:30"}
    (_doc, meta) = parse_edinet_documents_list_payload(_body([row]), retrieved_at=_RETRIEVED_AT)[0]
    assert meta.submitted_at is not None
    assert meta.submitted_at.tzinfo is not None
    assert meta.submitted_at.utcoffset().total_seconds() == 9 * 3600


def test_process_datetime_is_not_treated_as_public_timestamp() -> None:
    """processDateTime(公式仕様: Documents List自体の更新日時)は、Document
    公開時刻(market_public_at)ともDocumentの内容とも無関係であることを、
    Common Coreへ一切反映しないことで示す(D0046 §10)。"""
    row = {"docID": "D1", "processDateTime": "2026-08-17 09:00"}
    (doc, meta) = parse_edinet_documents_list_payload(_body([row]), retrieved_at=_RETRIEVED_AT)[0]
    assert meta.process_at is not None
    assert doc.market_public_at is None


def test_malformed_timestamp_fails_closed_to_none_not_guessed() -> None:
    row = {"docID": "D1", "submitDateTime": "not-a-real-timestamp"}
    (_doc, meta) = parse_edinet_documents_list_payload(_body([row]), retrieved_at=_RETRIEVED_AT)[0]
    assert meta.submitted_at is None


# --- DocumentKind(公式別紙1のCode Listを確認するまでMappingしない) ---


def test_doc_type_code_never_mapped_to_document_kind_this_phase() -> None:
    """Local観測時の説明文(docDescription)から`docTypeCode`の意味を推測して
    DocumentKindへMappingすることは、Substring Heuristicと同じ危険性を持つため
    行わない(D0046 §14)。公式別紙1のCode Listを確認するまでは常にUNKNOWN。"""
    row = {"docID": "D1", "docTypeCode": "140", "docDescription": "四半期報告書"}
    (doc, meta) = parse_edinet_documents_list_payload(_body([row]), retrieved_at=_RETRIEVED_AT)[0]
    assert doc.document_kind == DocumentKind.UNKNOWN
    assert meta.doc_type_code == "140"  # Raw値はEDINET固有Metadataに保持する


# --- internal_document_id / Historical Retrieval Honesty ---


def test_internal_document_id_deterministic_and_index_based() -> None:
    rows = [{"docID": "D1"}, {"docID": "D2"}]
    parsed = parse_edinet_documents_list_payload(_body(rows), retrieved_at=_RETRIEVED_AT)
    assert parsed[0][0].internal_document_id == "EDINET_D1_0"
    assert parsed[1][0].internal_document_id == "EDINET_D2_1"


def test_parse_function_has_no_as_of_or_historical_reconstruction_parameter() -> None:
    """この関数は「今取得したRaw Payload」を変換するのみで、過去時点の
    Universe/Availabilityを再構成すると主張する引数を一切持たない
    (D0046 §7/§8 — Historical List Is Mutableという既知の制約を、
    実装のInterface自体にも反映する)。"""
    import inspect

    sig = inspect.signature(parse_edinet_documents_list_payload)
    assert "as_of" not in sig.parameters
    assert "historical" not in " ".join(sig.parameters).lower()


# --- Offline再現性 / Determinism ---


def test_parse_is_pure_and_deterministic_for_same_input() -> None:
    row = {"docID": "D1", "secCode": "72030", "withdrawalStatus": "1"}
    body = _body([row])
    result_a = parse_edinet_documents_list_payload(body, retrieved_at=_RETRIEVED_AT)
    result_b = parse_edinet_documents_list_payload(body, retrieved_at=_RETRIEVED_AT)
    assert result_a[0][0].internal_document_id == result_b[0][0].internal_document_id
    assert result_a[0][1].filer_sec_code == result_b[0][1].filer_sec_code
    assert result_a[0][1].withdrawal_status == result_b[0][1].withdrawal_status


# --- normalizer_version ---


def test_normalizer_version_records_edinet_specific_suffix() -> None:
    row = {"docID": "D1"}
    (doc, _meta) = parse_edinet_documents_list_payload(_body([row]), retrieved_at=_RETRIEVED_AT)[0]
    assert "EDINET" in doc.normalizer_version
