"""Phase4B-2(D0046追記): EdinetAdapter -> RawSnapshotStore -> edinet_normalize の
統合テスト(Offline再現性・Append-only・Binary Hash安定性)。外部呼び出しは
一切行わない(`requests.Session`をMock)。
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from lib.disclosures.providers.edinet import EdinetAdapter
from lib.disclosures.providers.edinet_normalize import parse_edinet_documents_list_payload
from lib.errors import AppendOnlyViolationError
from lib.snapshot import RawSnapshotStore


class _RecordingSession:
    def __init__(self, json_body: object) -> None:
        self._json_body = json_body

    def get(self, url: str, *, params: dict[str, object], headers: dict[str, str], timeout: int) -> object:
        json_body = self._json_body

        class _Resp:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> object:
                return json_body

        return _Resp()


_SUCCESS_BODY = {
    "metadata": {"status": "200", "resultset": {"count": 1}},
    "results": [{"docID": "S100TD9S", "secCode": "72030", "docDescription": "四半期報告書"}],
}


def test_raw_snapshot_append_only_rejects_overwrite(tmp_path: Path) -> None:
    """過去に保存したSnapshotを、同じsnapshot_idで(たとえ実際のAPI側の
    Historical Listが後から変わっていても)上書きできないことを確認する
    (D0046 §7「Historical List Is Mutable」に対する防御 — このLab側の
    保存物自体はAppend-onlyのまま守られる)。"""
    result = EdinetAdapter(api_key="k", session=_RecordingSession(_SUCCESS_BODY)).fetch_documents_list_raw(  # type: ignore[arg-type]
        date(2024, 5, 8), list_type=2
    )

    store = RawSnapshotStore(tmp_path)
    store.save(result, snapshot_id="edinet_2024-05-08_v1")

    # 「今」同じ日付を再取得しても(EDINET側で内容が更新されていても)、
    # 同じsnapshot_idでは上書きできない — 新しいsnapshot_idを発行する必要がある。
    # 別Adapterインスタンスを使うことで_throttle()の実待機を回避する(Test高速化)。
    result_again = EdinetAdapter(api_key="k", session=_RecordingSession(_SUCCESS_BODY)).fetch_documents_list_raw(  # type: ignore[arg-type]
        date(2024, 5, 8), list_type=2
    )
    with pytest.raises(AppendOnlyViolationError):
        store.save(result_again, snapshot_id="edinet_2024-05-08_v1")


def test_offline_replay_from_saved_snapshot_makes_no_network_call(tmp_path: Path) -> None:
    """保存済みSnapshotからのNormalize(Offline再現性、D0042原則)。
    `RawSnapshotStore.load()`はネットワーク呼び出しを一切行わず、Normalizer
    もPure Function(引数のみに依存)であることを確認する。"""
    adapter = EdinetAdapter(api_key="k", session=_RecordingSession(_SUCCESS_BODY))  # type: ignore[arg-type]
    result = adapter.fetch_documents_list_raw(date(2024, 5, 8), list_type=2)

    store = RawSnapshotStore(tmp_path)
    manifest = store.save(result, snapshot_id="edinet_2024-05-08_offline")

    # ここから先はSessionもAdapterも一切使わない(Offline)。
    _loaded_manifest, payload = store.load("EDINET", "edinet_2024-05-08_offline")
    parsed = parse_edinet_documents_list_payload(payload, retrieved_at=result.retrieved_at, raw_snapshot_ref=manifest.snapshot_id)

    assert len(parsed) == 1
    document, doc_metadata = parsed[0]
    assert document.source_document_id == "S100TD9S"
    assert doc_metadata.filer_sec_code == "72030"
    assert document.raw_snapshot_ref == "edinet_2024-05-08_offline"


def test_binary_content_hash_stable_across_repeated_computation(tmp_path: Path) -> None:
    """同じバイト列に対するSHA-256は常に同じ値になる(自明な性質だが、
    Byte-for-Byte Integrityの回帰確認として明示的にTestする)。"""

    class _DownloadSession:
        def get(self, url: str, *, params: dict[str, object], headers: dict[str, str], timeout: int) -> object:
            class _Resp:
                def raise_for_status(self) -> None:
                    return None

                content = b"\x50\x4b\x03\x04" + b"stable-content"

                @property
                def headers(self) -> dict[str, str]:
                    return {"Content-Type": "application/octet-stream"}

            return _Resp()

    # 別々のAdapterインスタンスを使うことで、_throttle()による実待機
    # (レート制限、5秒間隔)を回避する(Test高速化、Rate Limit挙動自体は
    # test_edinet_adapter.pyの別Testで確認済み)。
    result_a = EdinetAdapter(api_key="k", session=_DownloadSession()).fetch_document_raw("S100TD9S", download_type=1)  # type: ignore[arg-type]
    result_b = EdinetAdapter(api_key="k", session=_DownloadSession()).fetch_document_raw("S100TD9S", download_type=1)  # type: ignore[arg-type]
    assert result_a.payload["raw_retrieval_hash"] == result_b.payload["raw_retrieval_hash"]

    store = RawSnapshotStore(tmp_path)
    store.save(result_a, snapshot_id="edinet_doc_S100TD9S")
    _loaded_manifest, loaded_payload = store.load("EDINET", "edinet_doc_S100TD9S")
    assert loaded_payload["raw_retrieval_hash"] == result_a.payload["raw_retrieval_hash"]
    assert json.dumps(loaded_payload, sort_keys=True) == json.dumps(result_a.payload, sort_keys=True)
