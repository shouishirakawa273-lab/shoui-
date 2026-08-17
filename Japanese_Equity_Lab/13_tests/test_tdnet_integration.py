"""Phase4B-3(D0048): TdnetAdapter -> RawSnapshotStore -> tdnet_normalize の
統合テスト(Offline再現性・Append-only・Evidence生成)。外部呼び出しは
一切行わない(`requests.Session`をMock)。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from lib.disclosures.evidence import disclosure_document_to_evidence
from lib.disclosures.providers.tdnet import TdnetAdapter
from lib.disclosures.providers.tdnet_cursor import TdnetRetrievalCursorState
from lib.disclosures.providers.tdnet_normalize import extract_retrieval_cursor_fields, parse_tdnet_documents_list_payload
from lib.disclosures.view import disclosures_as_of
from lib.errors import AppendOnlyViolationError
from lib.evidence.model import AvailabilitySemantics
from lib.snapshot import RawSnapshotStore
from lib.sources.catalog import SourceAuthorityClass


class _RecordingSession:
    def __init__(self, json_body: object) -> None:
        self._json_body = json_body

    def get(self, url: str, *, params: dict[str, object], headers: dict[str, str], timeout: int) -> object:
        json_body = self._json_body

        class _Resp:
            status_code = 200
            headers: dict[str, str] = {}

            def raise_for_status(self) -> None:
                return None

            def json(self) -> object:
                return json_body

        return _Resp()


_SUCCESS_BODY = {
    "data": [
        {
            "DiscNo": "20260817001",
            "Code": "72030",
            "Name": "トヨタ自動車",
            "DiscDate": "2026-08-17",
            "DiscTime": "15:00",
            "Title": "決算短信〔IFRS〕(連結)",
            "DiscStatus": None,
            "RevNo": 1,
            "DiscItems": ["01"],
            "Docs": {"pdf": "https://example.invalid/full.pdf"},
        }
    ],
    "cursor": "cursor-next-abc",
    "pagination_key": None,
}


def test_raw_snapshot_append_only_rejects_overwrite(tmp_path: Path) -> None:
    result = TdnetAdapter(api_key="k", session=_RecordingSession(_SUCCESS_BODY)).fetch_documents_list_raw(  # type: ignore[arg-type]
        target_date=date(2026, 8, 17)
    )
    store = RawSnapshotStore(tmp_path)
    store.save(result, snapshot_id="tdnet_2026-08-17_v1")

    result_again = TdnetAdapter(api_key="k", session=_RecordingSession(_SUCCESS_BODY)).fetch_documents_list_raw(  # type: ignore[arg-type]
        target_date=date(2026, 8, 17)
    )
    with pytest.raises(AppendOnlyViolationError):
        store.save(result_again, snapshot_id="tdnet_2026-08-17_v1")


def test_offline_replay_from_saved_snapshot_makes_no_network_call(tmp_path: Path) -> None:
    adapter = TdnetAdapter(api_key="k", session=_RecordingSession(_SUCCESS_BODY))  # type: ignore[arg-type]
    result = adapter.fetch_documents_list_raw(target_date=date(2026, 8, 17))

    store = RawSnapshotStore(tmp_path)
    manifest = store.save(result, snapshot_id="tdnet_2026-08-17_offline")

    # ここから先はSessionもAdapterも一切使わない(Offline)。
    _loaded_manifest, payload = store.load("TDNET", "tdnet_2026-08-17_offline")
    parsed = parse_tdnet_documents_list_payload(payload, retrieved_at=result.retrieved_at, raw_snapshot_ref=manifest.snapshot_id)

    assert len(parsed) == 1
    document, meta = parsed[0]
    assert document.source_document_id == "20260817001"
    assert meta.provider_code == "72030"
    assert document.raw_snapshot_ref == "tdnet_2026-08-17_offline"


def test_cursor_extraction_and_retrieval_state_construction_stay_offline(tmp_path: Path) -> None:
    """保存済みSnapshotからCursorを抽出し、`TdnetRetrievalCursorState`を構築する
    経路もOfflineで完結すること(Cursor StateはDisclosureDocumentとは独立に
    保持される、`TDNET_ARCHITECTURE.md` §4)。"""
    from datetime import UTC, datetime

    adapter = TdnetAdapter(api_key="k", session=_RecordingSession(_SUCCESS_BODY))  # type: ignore[arg-type]
    result = adapter.fetch_documents_list_raw(target_date=date(2026, 8, 17))

    store = RawSnapshotStore(tmp_path)
    store.save(result, snapshot_id="tdnet_2026-08-17_cursor")
    _manifest, payload = store.load("TDNET", "tdnet_2026-08-17_cursor")

    cursor, pagination_key = extract_retrieval_cursor_fields(payload)
    assert cursor == "cursor-next-abc"
    assert pagination_key is None

    cursor_state = TdnetRetrievalCursorState(
        query_date=date(2026, 8, 17),
        cursor_value=cursor,
        previous_cursor=None,
        retrieved_at=datetime(2026, 8, 17, 12, 0, tzinfo=UTC),
    )
    assert cursor_state.cursor_value == "cursor-next-abc"


def test_normalized_document_flows_into_evidence_and_market_information_study_view(tmp_path: Path) -> None:
    """正規化されたDocumentが、既存のProvider-neutral Evidence生成
    (`disclosure_document_to_evidence`)・As-of View(`disclosures_as_of`、
    A系統=Market Information Study)へそのまま流し込めることを確認する
    (D0045のCommon Coreが、実TDnet Dataに対しても変更なく機能することの
    回帰確認)。"""
    from datetime import UTC, datetime

    adapter = TdnetAdapter(api_key="k", session=_RecordingSession(_SUCCESS_BODY))  # type: ignore[arg-type]
    result = adapter.fetch_documents_list_raw(target_date=date(2026, 8, 17))
    parsed = parse_tdnet_documents_list_payload(result.payload, retrieved_at=result.retrieved_at)
    document, _meta = parsed[0]

    evidence = disclosure_document_to_evidence(document, source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL)
    assert evidence.source.available_at == document.market_public_at

    # A系統(Market Information Study): market_public_atが確認済み(EXACT)なので
    # decision_atがそれ以降であれば見える。
    decision_at = datetime(2026, 8, 17, 16, 0, tzinfo=UTC)
    visible = disclosures_as_of([document], decision_at, availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT)
    assert document in visible

    # B系統(既定、Provider Available At): provider_available_atは常にUNKNOWNの
    # ままなので、既定では見えない(include_unknown_availability=Falseが既定)。
    visible_b = disclosures_as_of([document], decision_at)
    assert document not in visible_b
