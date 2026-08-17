"""Phase4B-3(D0048): `lib.disclosures.providers.tdnet_normalize`のテスト。

Field名・意味論は`EXTERNAL_OFFICIAL_SPEC_VERIFICATION`(ユーザーが別のWeb-access
環境から確認したと申告した内容)に基づく。Claude自身がこのSession内でFetchして
確認したものではない(`TDNET_SOURCE_ONBOARDING.md`参照)。
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from lib.disclosures.model import DisclosureDocument, DocumentKind
from lib.disclosures.providers.tdnet_normalize import (
    TDNET_NORMALIZER_VERSION,
    TdnetDiscStatus,
    TdnetDocumentMetadata,
    extract_retrieval_cursor_fields,
    parse_tdnet_documents_list_payload,
)
from lib.errors import DataSourceError
from lib.evidence.model import AvailabilityBasis

_RETRIEVED_AT = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)

_FULL_ROW = {
    "DiscNo": "20260817001",
    "Code": "72030",
    "Name": "トヨタ自動車",
    "DiscDate": "2026-08-17",
    "DiscTime": "15:00",
    "Title": "決算短信〔IFRS〕(連結)",
    "DiscStatus": None,
    "RevNo": 1,
    "DiscItems": ["01", "02"],
    "Docs": {"pdf": "https://example.invalid/full.pdf"},
}


def _payload(rows: list[dict[str, object]], *, cursor: str | None = "c1", pagination_key: str | None = None) -> dict[str, object]:
    return {"data": rows, "cursor": cursor, "pagination_key": pagination_key}


# --- Envelope Validation ---


def test_parse_raises_when_data_key_missing() -> None:
    with pytest.raises(DataSourceError, match="data"):
        parse_tdnet_documents_list_payload({"cursor": None}, retrieved_at=_RETRIEVED_AT)


def test_parse_raises_when_data_is_not_a_list() -> None:
    with pytest.raises(DataSourceError, match="data"):
        parse_tdnet_documents_list_payload({"data": "not-a-list"}, retrieved_at=_RETRIEVED_AT)


def test_parse_skips_non_mapping_rows_without_raising() -> None:
    parsed = parse_tdnet_documents_list_payload(_payload([_FULL_ROW, "not-a-row"]), retrieved_at=_RETRIEVED_AT)
    assert len(parsed) == 1


# --- Field Mapping(基本) ---


def test_parse_full_row_maps_basic_fields() -> None:
    parsed = parse_tdnet_documents_list_payload(_payload([_FULL_ROW]), retrieved_at=_RETRIEVED_AT, raw_snapshot_ref="snap1")
    document, meta = parsed[0]

    assert isinstance(document, DisclosureDocument)
    assert isinstance(meta, TdnetDocumentMetadata)
    assert document.source_document_id == "20260817001"
    assert document.title == "決算短信〔IFRS〕(連結)"
    assert document.originating_source == "TDnet"
    assert document.delivery_provider == "J-Quants"
    assert document.raw_snapshot_ref == "snap1"
    assert document.normalizer_version == TDNET_NORMALIZER_VERSION
    assert meta.disc_no == "20260817001"
    assert meta.provider_code == "72030"
    assert meta.name == "トヨタ自動車"


def test_no_attachment_materialization_ephemeral_urls_never_become_permanent_field() -> None:
    """`/v2/td/files`/`/v2/td/bulk`のDownload URLは15分で失効する(EXTERNAL_
    OFFICIAL_SPEC_VERIFICATION §5/§6)。このNormalizerは`DisclosureAttachment`
    を一切生成しない(Phase4B-1の既存方針を踏襲)ため、`Docs`Field内のURLらしき
    値が`DisclosureDocument`のいかなる永続的Fieldへも紛れ込まないことを確認する
    (`TDNET_ARCHITECTURE.md` §5「Ephemeral URL Safety」)。"""
    row = dict(_FULL_ROW)
    row["Docs"] = {"pdf": "https://example.invalid/should-not-become-permanent.pdf"}
    parsed = parse_tdnet_documents_list_payload(_payload([row]), retrieved_at=_RETRIEVED_AT)
    document, meta = parsed[0]
    assert document.attachments == ()
    # URL自体はOpaqueなRaw値としてMetadata側にのみ残る(Common Coreへは持ち込まない)。
    assert "should-not-become-permanent.pdf" in (meta.docs_raw or "")
    assert "should-not-become-permanent.pdf" not in document.title


def test_parse_title_missing_uses_placeholder() -> None:
    row = dict(_FULL_ROW)
    del row["Title"]
    parsed = parse_tdnet_documents_list_payload(_payload([row]), retrieved_at=_RETRIEVED_AT)
    document, _ = parsed[0]
    assert "Title unavailable" in document.title
    assert "20260817001" in document.title


# --- document_kind: 意図的に常にUNKNOWN(DiscItems公式Code List未確認) ---


def test_document_kind_is_always_unknown() -> None:
    parsed = parse_tdnet_documents_list_payload(_payload([_FULL_ROW]), retrieved_at=_RETRIEVED_AT)
    document, _ = parsed[0]
    assert document.document_kind == DocumentKind.UNKNOWN


def test_disc_items_and_docs_kept_as_opaque_raw_values() -> None:
    parsed = parse_tdnet_documents_list_payload(_payload([_FULL_ROW]), retrieved_at=_RETRIEVED_AT)
    _, meta = parsed[0]
    # listやdictはJSON文字列化されて保持される(意味論を一切解釈しない)。
    assert meta.disc_items_raw is not None
    assert "01" in meta.disc_items_raw
    assert meta.docs_raw is not None
    assert "full.pdf" in meta.docs_raw


def test_disc_items_as_plain_string_kept_verbatim() -> None:
    row = dict(_FULL_ROW)
    row["DiscItems"] = "01"
    parsed = parse_tdnet_documents_list_payload(_payload([row]), retrieved_at=_RETRIEVED_AT)
    _, meta = parsed[0]
    assert meta.disc_items_raw == "01"


# --- entity_id: Code正規化(既存D0036パターンの再利用) ---


def test_entity_id_normalized_from_five_digit_common_stock_code() -> None:
    parsed = parse_tdnet_documents_list_payload(_payload([_FULL_ROW]), retrieved_at=_RETRIEVED_AT)
    document, _ = parsed[0]
    assert document.entity_id == "7203"


def test_entity_id_falls_back_to_none_for_unnormalizable_code() -> None:
    row = dict(_FULL_ROW)
    row["Code"] = "72031"  # 末尾が"0"でない5桁 -> 正規化不可(優先株等の可能性)
    parsed = parse_tdnet_documents_list_payload(_payload([row]), retrieved_at=_RETRIEVED_AT)
    document, meta = parsed[0]
    assert document.entity_id is None
    assert meta.provider_code == "72031"  # Raw値は保持される


def test_entity_id_none_when_code_missing() -> None:
    row = dict(_FULL_ROW)
    del row["Code"]
    parsed = parse_tdnet_documents_list_payload(_payload([row]), retrieved_at=_RETRIEVED_AT)
    document, _ = parsed[0]
    assert document.entity_id is None


# --- market_public_at(EXTERNAL_OFFICIAL_SPEC_VERIFICATION §7、PIT最重要) ---


def test_market_public_at_built_from_disc_date_and_disc_time_with_exact_basis() -> None:
    parsed = parse_tdnet_documents_list_payload(_payload([_FULL_ROW]), retrieved_at=_RETRIEVED_AT)
    document, _ = parsed[0]
    assert document.market_public_at is not None
    assert document.market_public_at.tzinfo is not None
    assert document.market_public_at.year == 2026
    assert document.market_public_at.month == 8
    assert document.market_public_at.day == 17
    assert document.market_public_at.hour == 15
    assert document.market_public_at.minute == 0
    assert document.market_public_at_basis == AvailabilityBasis.EXACT


def test_market_public_at_unknown_when_disc_time_missing() -> None:
    row = dict(_FULL_ROW)
    del row["DiscTime"]
    parsed = parse_tdnet_documents_list_payload(_payload([row]), retrieved_at=_RETRIEVED_AT)
    document, _ = parsed[0]
    assert document.market_public_at is None
    assert document.market_public_at_basis == AvailabilityBasis.UNKNOWN


def test_market_public_at_unknown_when_disc_date_missing() -> None:
    row = dict(_FULL_ROW)
    del row["DiscDate"]
    parsed = parse_tdnet_documents_list_payload(_payload([row]), retrieved_at=_RETRIEVED_AT)
    document, _ = parsed[0]
    assert document.market_public_at is None
    assert document.market_public_at_basis == AvailabilityBasis.UNKNOWN


def test_market_public_at_unknown_on_malformed_time() -> None:
    row = dict(_FULL_ROW)
    row["DiscTime"] = "not-a-time"
    parsed = parse_tdnet_documents_list_payload(_payload([row]), retrieved_at=_RETRIEVED_AT)
    document, _ = parsed[0]
    assert document.market_public_at is None
    assert document.market_public_at_basis == AvailabilityBasis.UNKNOWN


def test_provider_available_at_always_unknown_no_fallback() -> None:
    """market_public_atが確認できても、provider_available_atへFallbackしない
    (D0043/D0045と同じ保守的方針、EXTERNAL_OFFICIAL_SPEC_VERIFICATION §7)。"""
    parsed = parse_tdnet_documents_list_payload(_payload([_FULL_ROW]), retrieved_at=_RETRIEVED_AT)
    document, _ = parsed[0]
    assert document.provider_available_at is None
    assert document.provider_available_at_basis == AvailabilityBasis.UNKNOWN


# --- DiscStatus: Schema宣言値のParse(現在の実装挙動=常にnullとは別軸) ---


def test_disc_status_null_maps_to_new_per_schema() -> None:
    parsed = parse_tdnet_documents_list_payload(_payload([_FULL_ROW]), retrieved_at=_RETRIEVED_AT)
    _, meta = parsed[0]
    assert meta.disc_status == TdnetDiscStatus.NEW


def test_disc_status_revision_maps_correctly() -> None:
    row = dict(_FULL_ROW)
    row["DiscStatus"] = "revision"
    parsed = parse_tdnet_documents_list_payload(_payload([row]), retrieved_at=_RETRIEVED_AT)
    _, meta = parsed[0]
    assert meta.disc_status == TdnetDiscStatus.REVISION


def test_disc_status_delete_maps_correctly() -> None:
    row = dict(_FULL_ROW)
    row["DiscStatus"] = "delete"
    parsed = parse_tdnet_documents_list_payload(_payload([row]), retrieved_at=_RETRIEVED_AT)
    _, meta = parsed[0]
    assert meta.disc_status == TdnetDiscStatus.DELETE


def test_disc_status_unknown_value_fails_closed() -> None:
    row = dict(_FULL_ROW)
    row["DiscStatus"] = "some-future-value"
    parsed = parse_tdnet_documents_list_payload(_payload([row]), retrieved_at=_RETRIEVED_AT)
    _, meta = parsed[0]
    assert meta.disc_status == TdnetDiscStatus.UNKNOWN


# --- RevNo: 単なるRaw値保持(Revision回数のEvidenceとして解釈しない) ---


def test_rev_no_parsed_as_int() -> None:
    parsed = parse_tdnet_documents_list_payload(_payload([_FULL_ROW]), retrieved_at=_RETRIEVED_AT)
    _, meta = parsed[0]
    assert meta.rev_no == 1


def test_rev_no_none_when_missing() -> None:
    row = dict(_FULL_ROW)
    del row["RevNo"]
    parsed = parse_tdnet_documents_list_payload(_payload([row]), retrieved_at=_RETRIEVED_AT)
    _, meta = parsed[0]
    assert meta.rev_no is None


def test_rev_no_fails_closed_to_none_on_malformed_value() -> None:
    row = dict(_FULL_ROW)
    row["RevNo"] = "not-a-number"
    parsed = parse_tdnet_documents_list_payload(_payload([row]), retrieved_at=_RETRIEVED_AT)
    _, meta = parsed[0]
    assert meta.rev_no is None


def test_source_version_reflects_rev_no_but_is_not_a_relationship() -> None:
    """source_versionはRaw値の記録に過ぎず、それ自体がRevision Relationshipを
    意味しない(`DisclosureDocument.source_version`の既存Docstring原則)。"""
    parsed = parse_tdnet_documents_list_payload(_payload([_FULL_ROW]), retrieved_at=_RETRIEVED_AT)
    document, _ = parsed[0]
    assert document.source_version == "1"


# --- Schema Evolution Version Marker(TDNET_ARCHITECTURE.md §2) ---


def test_schema_evolution_markers_present() -> None:
    parsed = parse_tdnet_documents_list_payload(_payload([_FULL_ROW]), retrieved_at=_RETRIEVED_AT)
    _, meta = parsed[0]
    assert meta.provider_schema_version == "EXTERNAL_OFFICIAL_SPEC_VERIFICATION_2026-08-17"
    assert meta.observed_behavior_documented_at == date(2026, 8, 17)


# --- Cursor抽出(DisclosureDocumentとは分離したまま) ---


def test_extract_retrieval_cursor_fields_reads_top_level_envelope() -> None:
    cursor, pagination_key = extract_retrieval_cursor_fields(_payload([_FULL_ROW], cursor="c1", pagination_key=None))
    assert cursor == "c1"
    assert pagination_key is None


def test_extract_retrieval_cursor_fields_does_not_touch_document_rows() -> None:
    """Cursor抽出はEnvelope Top-levelのみを見る。Document Row側にcursor値が
    紛れ込んでいても(想定外の形状)、これはDocument自体のFieldへは反映されない
    ことを確認する(構造的分離の再確認)。"""
    payload = _payload([_FULL_ROW], cursor="top-level-cursor")
    parsed = parse_tdnet_documents_list_payload(payload, retrieved_at=_RETRIEVED_AT)
    document, meta = parsed[0]
    # DisclosureDocument/TdnetDocumentMetadataのいずれにも"cursor"という概念の
    # Fieldが存在しないことを型的に保証する(dataclass fields集合で確認)。
    import dataclasses

    assert "cursor" not in {f.name for f in dataclasses.fields(document)}
    assert "cursor" not in {f.name for f in dataclasses.fields(meta)}


# --- 訂正Relationship自動生成禁止(タスク上最重要、構造的確認) ---


def test_tdnet_normalize_never_constructs_document_relationship() -> None:
    """新しいDiscNoが過去のDiscNoを訂正した、という関係性Recordを一切生成
    しないことを、Import構造で確認する(関係性RecordのType名自体は
    `lib.disclosures.model`にのみ存在し、このModuleでは一切参照しない)。"""
    import lib.disclosures.providers.tdnet_normalize as tdnet_normalize_module

    source = tdnet_normalize_module.__file__
    assert source is not None
    with open(source, encoding="utf-8") as f:
        text = f.read()
    assert "DocumentRelationship" not in text
    assert "DuplicateRelationKind" not in text


def test_multiple_rows_with_different_disc_no_produce_independent_documents_no_auto_link() -> None:
    """開示File自体が訂正され新DiscNoが発行された場合でも(ユーザー申告の
    現在の実装挙動)、旧DiscNoとの関係を推測で結び付けない — 単に独立した
    2つのDocumentとして正規化されることを確認する。"""
    row_old = dict(_FULL_ROW)
    row_old["DiscNo"] = "20260817001"
    row_new = dict(_FULL_ROW)
    row_new["DiscNo"] = "20260817002"
    parsed = parse_tdnet_documents_list_payload(_payload([row_old, row_new]), retrieved_at=_RETRIEVED_AT)
    assert len(parsed) == 2
    ids = {doc.source_document_id for doc, _ in parsed}
    assert ids == {"20260817001", "20260817002"}
