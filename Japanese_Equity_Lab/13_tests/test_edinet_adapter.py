"""Phase4B-2(EDINET V2): `lib.disclosures.providers.edinet.EdinetAdapter`のテスト。

`EdinetAdapter`はRaw HTTP Fetchのみを提供し(Field-level Normalizationは行わない)、
実ネットワーク呼び出しは一切行わない(`requests.Session`をMockする、ルートCLAUDE.md
「外部API呼び出しは...テストでモックする」に従う)。
"""

from __future__ import annotations

import base64
import json
from datetime import date

import pytest
import requests
from lib.disclosures.providers.edinet import BASE_URL, EdinetAdapter
from lib.errors import DataSourceError


class _RecordingSession:
    def __init__(self, json_body: object = None, *, content: bytes = b"", content_type: str = "application/json") -> None:
        self.calls: list[dict[str, object]] = []
        self._json_body = json_body if json_body is not None else {"ok": True}
        self._content = content
        self._content_type = content_type

    def get(self, url: str, *, params: dict[str, object], headers: dict[str, str], timeout: int) -> object:
        self.calls.append({"url": url, "params": dict(params), "headers": dict(headers), "timeout": timeout})
        json_body = self._json_body
        content = self._content
        content_type = self._content_type

        class _Resp:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> object:
                return json_body

            @property
            def content(self) -> bytes:
                return content

            @property
            def headers(self) -> dict[str, str]:
                return {"Content-Type": content_type}

        return _Resp()


class _FailingSession:
    def get(self, *args: object, **kwargs: object) -> None:
        raise requests.exceptions.ConnectionError(f"failed to connect (params={kwargs.get('params')})")


class _NonJsonSession:
    def get(self, *args: object, **kwargs: object) -> object:
        class _Resp:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> object:
                raise ValueError("not json")

        return _Resp()


# --- 未設定時の挙動 ---


def test_edinet_adapter_unconfigured_raises_data_source_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EDINET_API_KEY", raising=False)
    adapter = EdinetAdapter(api_key=None)
    assert adapter.configured is False
    with pytest.raises(DataSourceError, match="EDINET_API_KEY"):
        adapter.fetch_documents_list_raw(date(2024, 5, 8))
    with pytest.raises(DataSourceError, match="EDINET_API_KEY"):
        adapter.fetch_document_raw("S100XXXX", download_type=1)


def test_edinet_adapter_configured_true_when_key_present() -> None:
    adapter = EdinetAdapter(api_key="test-key")
    assert adapter.configured is True


# --- 認証方式(query_param / header)の候補実装 ---


def test_edinet_adapter_query_param_auth_style_puts_key_in_outgoing_params_only() -> None:
    session = _RecordingSession()
    adapter = EdinetAdapter(api_key="secret-key-abc", session=session, auth_style="query_param")  # type: ignore[arg-type]
    result = adapter.fetch_documents_list_raw(date(2024, 5, 8), list_type=2)

    assert len(session.calls) == 1
    call = session.calls[0]
    assert call["params"]["Subscription-Key"] == "secret-key-abc"
    assert call["headers"] == {}
    # Snapshotへ記録される側にはAPIキーが一切含まれない。
    assert "Subscription-Key" not in result.request_parameters
    assert result.request_parameters == {"date": "2024-05-08", "type": "2"}


def test_edinet_adapter_header_auth_style_puts_key_in_headers_only() -> None:
    session = _RecordingSession()
    adapter = EdinetAdapter(api_key="secret-key-abc", session=session, auth_style="header")  # type: ignore[arg-type]
    result = adapter.fetch_documents_list_raw(date(2024, 5, 8), list_type=2)

    call = session.calls[0]
    assert call["headers"] == {"Ocp-Apim-Subscription-Key": "secret-key-abc"}
    assert "Subscription-Key" not in call["params"]
    assert result.request_parameters == {"date": "2024-05-08", "type": "2"}


def test_edinet_adapter_default_auth_style_is_query_param() -> None:
    adapter = EdinetAdapter(api_key="k")
    assert adapter._auth_style == "query_param"  # noqa: SLF001


# --- Documents List Raw Fetch ---


def test_fetch_documents_list_raw_returns_raw_payload_untouched() -> None:
    payload = {"metadata": {"resultset": {"count": 1}}, "results": [{"docID": "S100XXXX"}]}
    session = _RecordingSession(json_body=payload)
    adapter = EdinetAdapter(api_key="k", session=session)  # type: ignore[arg-type]
    result = adapter.fetch_documents_list_raw(date(2024, 5, 8), list_type=2)

    assert result.source == "EDINET"
    assert result.endpoint == "/documents.json"
    assert result.payload == payload  # Normalizationしていない、生のまま
    assert result.data_period == "2024-05-08"
    assert BASE_URL in str(session.calls[0]["url"])


def test_fetch_documents_list_raw_does_not_accept_code_or_date_range_arguments() -> None:
    """Documents List APIが日付範囲/銘柄コードクエリに対応しているかは未確認
    (EDINET_SOURCE_ONBOARDING.md §8)なので、そのような引数は意図的に持たせていない。"""
    import inspect

    sig = inspect.signature(EdinetAdapter.fetch_documents_list_raw)
    assert "codes" not in sig.parameters
    assert "start_date" not in sig.parameters
    assert "end_date" not in sig.parameters


def test_fetch_documents_list_raw_non_json_response_raises_data_source_error() -> None:
    adapter = EdinetAdapter(api_key="k", session=_NonJsonSession())  # type: ignore[arg-type]
    with pytest.raises(DataSourceError, match="JSON"):
        adapter.fetch_documents_list_raw(date(2024, 5, 8))


# --- Document Download Raw Fetch(スモークテスト用) ---


def test_fetch_document_raw_requires_explicit_download_type() -> None:
    """`download_type`に既定値を持たせない(情報源間で矛盾する候補値のいずれかを
    呼び出し側が明示的に選ぶことを強制する、EDINET_SOURCE_ONBOARDING.md §7)。"""
    import inspect

    sig = inspect.signature(EdinetAdapter.fetch_document_raw)
    assert sig.parameters["download_type"].default is inspect.Parameter.empty


def test_fetch_document_raw_base64_encodes_binary_content_round_trip() -> None:
    raw_bytes = b"\x50\x4b\x03\x04fake-zip-bytes"  # ZIPマジックナンバー風のダミー
    session = _RecordingSession(content=raw_bytes, content_type="application/octet-stream")
    adapter = EdinetAdapter(api_key="k", session=session)  # type: ignore[arg-type]
    result = adapter.fetch_document_raw("S100XXXX", download_type=1)

    assert result.payload["content_type"] == "application/octet-stream"
    decoded = base64.b64decode(result.payload["content_base64"])
    assert decoded == raw_bytes  # Byte-for-Byteの往復整合性


def test_fetch_document_raw_request_parameters_never_contain_secret() -> None:
    secret_key = "super-secret-edinet-key-xyz"
    session = _RecordingSession()
    adapter = EdinetAdapter(api_key=secret_key, session=session, auth_style="query_param")  # type: ignore[arg-type]
    result = adapter.fetch_document_raw("S100XXXX", download_type=1)
    assert secret_key not in json.dumps(result.request_parameters)


# --- 例外時のAPIキー非漏洩 ---


def test_edinet_adapter_connection_failure_does_not_leak_api_key_in_exception() -> None:
    secret_key = "super-secret-edinet-key-xyz"
    adapter = EdinetAdapter(api_key=secret_key, session=_FailingSession())  # type: ignore[arg-type]
    with pytest.raises(DataSourceError) as excinfo:
        adapter.fetch_documents_list_raw(date(2024, 5, 8))
    assert secret_key not in str(excinfo.value)
    assert excinfo.value.__cause__ is None  # 原例外をchainしない(URLにキーを含みうるため)


# --- Normalizer/Entity解決を一切呼ばないことの構造的確認 ---


def test_edinet_adapter_module_does_not_import_disclosures_normalize_or_view() -> None:
    """このAdapterはRaw Fetchのみ担い、正規化(normalize)・As-of View(view)には
    一切依存しないことをimport構造で確認する(未確認Field名を正規化に混入させない)。"""
    import lib.disclosures.providers.edinet as edinet_module

    source = edinet_module.__file__
    assert source is not None
    with open(source, encoding="utf-8") as f:
        text = f.read()
    import_lines = [line.strip() for line in text.splitlines() if line.strip().startswith(("import ", "from "))]
    forbidden_modules = ("lib.disclosures.normalize", "lib.disclosures.view", "lib.disclosures.model")
    assert not any(module in line for line in import_lines for module in forbidden_modules)
    assert "DisclosureDocument(" not in text
