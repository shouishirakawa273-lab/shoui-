"""Raw Snapshot: APIレスポンスを即座に加工して捨てず、Immutableな形で保存する。

01_data/raw/ 配下に、生のレスポンスペイロードと、後から同じBacktestを再現するための
manifest(source/endpoint/request_parameters/retrieved_at/data_period/
response_schema_version/content_hash/local_file/record_count)を必ずセットで保存する。
manifestにもペイロードにも認証情報(トークン・APIキー等)を含めない。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from lib.data_sources.base import RawFetchResult
from lib.errors import AppendOnlyViolationError
from lib.schemas.base import RecordMeta

_FORBIDDEN_PARAM_KEY_SUBSTRINGS = ("token", "key", "secret", "password", "authorization", "credential")


class SecretLeakageError(Exception):
    """request_parameters等にAPIキー・トークンらしき値が含まれている場合に送出する。"""


class SnapshotTamperedError(Exception):
    """保存済みRaw Snapshotのcontent_hashが実際のファイル内容と一致しない場合に送出する。"""


def _assert_no_secret_like_keys(request_parameters: dict[str, Any]) -> None:
    for key in request_parameters:
        lowered = key.lower()
        if any(bad in lowered for bad in _FORBIDDEN_PARAM_KEY_SUBSTRINGS):
            raise SecretLeakageError(
                f"request_parametersに認証情報らしきキー '{key}' が含まれています。"
                "Snapshotはリポジトリに保存されうるため、認証情報は絶対に含めないでください。"
            )


@dataclass(kw_only=True, frozen=True)
class SnapshotManifest(RecordMeta):
    """Raw Snapshot 1件分のmanifest。これだけで同じ取得を再現できることを目指す。"""

    snapshot_id: str
    source: str
    endpoint: str
    request_parameters: dict[str, Any]
    retrieved_at: str
    data_period: str
    response_schema_version: str
    content_hash: str
    local_file: str
    record_count: int


def _manifest_to_dict(manifest: SnapshotManifest) -> dict[str, Any]:
    payload = asdict(manifest)
    payload["created_at"] = manifest.created_at.isoformat()
    payload["updated_at"] = manifest.updated_at.isoformat()
    return payload


def _manifest_from_dict(data: dict[str, Any]) -> SnapshotManifest:
    d: dict[str, Any] = dict(data)
    d["created_at"] = datetime.fromisoformat(d["created_at"])
    d["updated_at"] = datetime.fromisoformat(d["updated_at"])
    return SnapshotManifest(**d)


class RawSnapshotStore:
    """01_data/raw/ 配下にImmutableなRaw Snapshotを保存・検証する。

    同じsnapshot_idへの再保存は拒否する(上書き禁止、追記のみ)。load()は
    保存時のcontent_hashと現在のファイル内容のhashを比較し、改変を検出する。
    """

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def _payload_path(self, source: str, snapshot_id: str) -> Path:
        return self._base_dir / source / f"{snapshot_id}.json"

    def _manifest_path(self, source: str, snapshot_id: str) -> Path:
        return self._base_dir / source / f"{snapshot_id}.manifest.json"

    def save(self, fetch_result: RawFetchResult, *, snapshot_id: str) -> SnapshotManifest:
        _assert_no_secret_like_keys(fetch_result.request_parameters)

        payload_path = self._payload_path(fetch_result.source, snapshot_id)
        manifest_path = self._manifest_path(fetch_result.source, snapshot_id)
        if payload_path.exists() or manifest_path.exists():
            raise AppendOnlyViolationError(
                f"snapshot_id={snapshot_id}(source={fetch_result.source}) は既に保存されています(上書き不可)"
            )

        payload_bytes = json.dumps(fetch_result.payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        content_hash = hashlib.sha256(payload_bytes).hexdigest()
        record_count = len(fetch_result.payload) if isinstance(fetch_result.payload, list) else 1

        payload_path.parent.mkdir(parents=True, exist_ok=True)
        payload_path.write_bytes(payload_bytes)

        manifest = SnapshotManifest(
            snapshot_id=snapshot_id,
            source=fetch_result.source,
            endpoint=fetch_result.endpoint,
            request_parameters=fetch_result.request_parameters,
            retrieved_at=fetch_result.retrieved_at.isoformat(),
            data_period=fetch_result.data_period,
            response_schema_version=fetch_result.response_schema_version,
            content_hash=content_hash,
            local_file=str(payload_path.relative_to(self._base_dir.parent)),
            record_count=record_count,
        )
        manifest_text = json.dumps(_manifest_to_dict(manifest), ensure_ascii=False, indent=2, sort_keys=True)
        manifest_path.write_text(manifest_text, encoding="utf-8")
        return manifest

    def load(self, source: str, snapshot_id: str) -> tuple[SnapshotManifest, Any]:
        """manifestとpayloadを読み込み、content_hashを検証する(改変検出)。"""
        manifest_path = self._manifest_path(source, snapshot_id)
        payload_path = self._payload_path(source, snapshot_id)
        if not manifest_path.exists() or not payload_path.exists():
            raise FileNotFoundError(f"snapshot_id={snapshot_id}(source={source}) が見つかりません")

        manifest = _manifest_from_dict(json.loads(manifest_path.read_text(encoding="utf-8")))

        payload_bytes = payload_path.read_bytes()
        actual_hash = hashlib.sha256(payload_bytes).hexdigest()
        if actual_hash != manifest.content_hash:
            raise SnapshotTamperedError(
                f"snapshot_id={snapshot_id} のcontent_hashが一致しません"
                f"(manifest={manifest.content_hash}, actual={actual_hash})。"
                "Raw Snapshotが保存後に改変された可能性があります。"
            )
        return manifest, json.loads(payload_bytes)
