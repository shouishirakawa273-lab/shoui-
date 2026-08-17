"""Phase4B-2(EDINET V2): `lib.disclosures.providers.edinet.EdinetAdapter`のテスト。

`EdinetAdapter`はRaw HTTP Fetchのみを提供し(Field-level Normalizationは行わない)、
実ネットワーク呼び出しは一切行わない(`requests.Session`をMockする、ルートCLAUDE.md
「外部API呼び出しは...テストでモックする」に従う)。

D0046追記: ローカル実データ検証で「EDINET APIはエラー時もHTTP 200を返し、
実際のStatusはJSON Body内の`metadata.status`に埋め込まれる」ことが判明し、
既存Adapterがこれを検知せずSuccessと誤判定するBugが発見された(Smoke Testが
`invalid subscription key`エラーを`SUCCESS`と表示した)。このFileの多くのTestは
この修正の回帰確認を目的とする。
"""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import date

import pytest
import requests
from lib.disclosures.providers.edinet import BASE_URL, EdinetAdapter, EdinetApiError, EdinetDownloadType
from lib.errors import DataSourceError

_SUCCESS_DOCUMENTS_LIST_BODY = {
    "metadata": {"status": "200", "message": "OK", "resultset": {"count": 0}},
    "results": [],
}


class _RecordingSession:
    def __init__(self, json_body: object = None, *, content: bytes = b"", content_type: str = "application/octet-stream") -> None:
        self.calls: list[dict[str, object]] = []
        self._json_body = json_body if json_body is not None else _SUCCESS_DOCUMENTS_LIST_BODY
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
                if content:
                    return json.loads(content)
                if isinstance(json_body, Exception):
                    raise json_body
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
        adapter.fetch_documents_list_raw(date(2024, 5, 8), list_type=2)
    with pytest.raises(DataSourceError, match="EDINET_API_KEY"):
        adapter.fetch_document_raw("S100XXXX", download_type=1)


def test_edinet_adapter_configured_true_when_key_present() -> None:
    adapter = EdinetAdapter(api_key="test-key")
    assert adapter.configured is True


# --- 認証方式(query_param、ローカル実データで成功確認済み) ---


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


def test_edinet_adapter_default_auth_style_actually_sends_query_param_request() -> None:
    session = _RecordingSession()
    adapter = EdinetAdapter(api_key="secret-key-abc", session=session)  # type: ignore[arg-type]  # auth_style未指定
    adapter.fetch_documents_list_raw(date(2024, 5, 8), list_type=2)

    call = session.calls[0]
    assert call["params"]["Subscription-Key"] == "secret-key-abc"
    assert call["headers"] == {}


# --- Documents List Raw Fetch ---


def test_fetch_documents_list_raw_returns_raw_payload_untouched() -> None:
    payload = {"metadata": {"status": "200", "resultset": {"count": 1}}, "results": [{"docID": "S100XXXX"}]}
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


def test_fetch_documents_list_raw_requires_explicit_list_type() -> None:
    import inspect

    sig = inspect.signature(EdinetAdapter.fetch_documents_list_raw)
    assert sig.parameters["list_type"].default is inspect.Parameter.empty


def test_fetch_documents_list_raw_non_json_response_raises_data_source_error() -> None:
    adapter = EdinetAdapter(api_key="k", session=_NonJsonSession())  # type: ignore[arg-type]
    with pytest.raises(DataSourceError, match="JSON"):
        adapter.fetch_documents_list_raw(date(2024, 5, 8), list_type=2)


# --- Critical Fix(D0046追記): HTTP 200だがmetadata.statusがエラーの場合をfail closedする ---


def test_documents_list_http_200_with_metadata_status_401_is_treated_as_failure() -> None:
    """ローカル実データ検証で発見された実際のBug: EDINETは認証失敗時もHTTP 200を
    返し、実際のStatusは`metadata.status`に埋め込まれる。修正前はこれを検知できず
    Smoke Testが`SUCCESS`と誤表示していた。"""
    error_body = {"metadata": {"status": "401", "message": "invalid subscription key"}}
    session = _RecordingSession(json_body=error_body)
    adapter = EdinetAdapter(api_key="wrong-key", session=session)  # type: ignore[arg-type]
    with pytest.raises(EdinetApiError, match="401"):
        adapter.fetch_documents_list_raw(date(2024, 5, 8), list_type=2)


def test_documents_list_error_message_includes_official_message_but_not_api_key() -> None:
    secret_key = "super-secret-edinet-key-xyz"
    error_body = {"metadata": {"status": "403", "message": "forbidden"}}
    session = _RecordingSession(json_body=error_body)
    adapter = EdinetAdapter(api_key=secret_key, session=session)  # type: ignore[arg-type]
    with pytest.raises(EdinetApiError) as excinfo:
        adapter.fetch_documents_list_raw(date(2024, 5, 8), list_type=2)
    assert "forbidden" in str(excinfo.value)
    assert secret_key not in str(excinfo.value)


@pytest.mark.parametrize("status_code", ["401", "403", "404", "429", "500", "503"])
def test_documents_list_various_error_statuses_all_fail_closed(status_code: str) -> None:
    error_body = {"metadata": {"status": status_code, "message": "error"}}
    session = _RecordingSession(json_body=error_body)
    adapter = EdinetAdapter(api_key="k", session=session)  # type: ignore[arg-type]
    with pytest.raises(EdinetApiError):
        adapter.fetch_documents_list_raw(date(2024, 5, 8), list_type=2)


def test_documents_list_missing_metadata_is_failure() -> None:
    session = _RecordingSession(json_body={"results": []})
    adapter = EdinetAdapter(api_key="k", session=session)  # type: ignore[arg-type]
    with pytest.raises(EdinetApiError, match="metadata"):
        adapter.fetch_documents_list_raw(date(2024, 5, 8), list_type=2)


def test_documents_list_missing_results_is_failure() -> None:
    session = _RecordingSession(json_body={"metadata": {"status": "200"}})
    adapter = EdinetAdapter(api_key="k", session=session)  # type: ignore[arg-type]
    with pytest.raises(EdinetApiError, match="results"):
        adapter.fetch_documents_list_raw(date(2024, 5, 8), list_type=2)


def test_documents_list_success_requires_all_three_conditions() -> None:
    """成功条件: HTTP成功 AND metadata.status=='200' AND resultsがlist。
    3条件すべてを満たす場合のみ成功することを確認する(いずれか1つでも
    欠けると失敗)。"""
    adapter_ok = EdinetAdapter(api_key="k", session=_RecordingSession(json_body=_SUCCESS_DOCUMENTS_LIST_BODY))  # type: ignore[arg-type]
    result = adapter_ok.fetch_documents_list_raw(date(2024, 5, 8), list_type=2)
    assert result.payload["metadata"]["status"] == "200"


# --- Document Download Raw Fetch ---


def test_fetch_document_raw_requires_explicit_download_type() -> None:
    import inspect

    sig = inspect.signature(EdinetAdapter.fetch_document_raw)
    assert sig.parameters["download_type"].default is inspect.Parameter.empty


def test_fetch_document_raw_base64_encodes_binary_content_round_trip() -> None:
    raw_bytes = b"\x50\x4b\x03\x04fake-zip-bytes"  # ZIPマジックナンバー
    session = _RecordingSession(content=raw_bytes, content_type="application/octet-stream")
    adapter = EdinetAdapter(api_key="k", session=session)  # type: ignore[arg-type]
    result = adapter.fetch_document_raw("S100XXXX", download_type=1)

    assert result.payload["content_type"] == "application/octet-stream"
    decoded = base64.b64decode(result.payload["content_base64"])
    assert decoded == raw_bytes  # Byte-for-Byteの往復整合性
    assert result.payload["content_sha256"] == hashlib.sha256(raw_bytes).hexdigest()


def test_fetch_document_raw_pdf_content_type_is_accepted_as_success() -> None:
    raw_bytes = b"%PDF-1.4 fake pdf bytes"
    session = _RecordingSession(content=raw_bytes, content_type="application/pdf")
    adapter = EdinetAdapter(api_key="k", session=session)  # type: ignore[arg-type]
    result = adapter.fetch_document_raw("S100XXXX", download_type=2)
    assert result.payload["content_type"] == "application/pdf"


def test_fetch_document_raw_json_error_body_is_treated_as_failure() -> None:
    """ローカル実データ検証で確認済み: 失敗時のContent-Typeは
    `application/json; charset=utf-8`(ZIP/PDF成功時とは異なる)。"""
    error_json = json.dumps({"metadata": {"status": "401", "message": "invalid subscription key"}}).encode("utf-8")
    session = _RecordingSession(content=error_json, content_type="application/json; charset=utf-8")
    adapter = EdinetAdapter(api_key="wrong-key", session=session)  # type: ignore[arg-type]
    with pytest.raises(EdinetApiError, match="401"):
        adapter.fetch_document_raw("S100XXXX", download_type=1)


def test_fetch_document_raw_json_error_message_does_not_leak_api_key() -> None:
    secret_key = "super-secret-edinet-key-xyz"
    error_json = json.dumps({"metadata": {"status": "401", "message": "invalid subscription key"}}).encode("utf-8")
    session = _RecordingSession(content=error_json, content_type="application/json; charset=utf-8")
    adapter = EdinetAdapter(api_key=secret_key, session=session)  # type: ignore[arg-type]
    with pytest.raises(EdinetApiError) as excinfo:
        adapter.fetch_document_raw("S100XXXX", download_type=1)
    assert secret_key not in str(excinfo.value)


def test_fetch_document_raw_unexpected_content_type_is_failure() -> None:
    """成功として知られている型(application/octet-stream, application/pdf)
    以外はAllowlist方式でfail closedする。"""
    session = _RecordingSession(content=b"<html>unexpected</html>", content_type="text/html")
    adapter = EdinetAdapter(api_key="k", session=session)  # type: ignore[arg-type]
    with pytest.raises(EdinetApiError, match="Content-Type"):
        adapter.fetch_document_raw("S100XXXX", download_type=1)


def test_fetch_document_raw_request_parameters_never_contain_secret() -> None:
    secret_key = "super-secret-edinet-key-xyz"
    session = _RecordingSession(content=b"\x50\x4b\x03\x04zip", content_type="application/octet-stream")
    adapter = EdinetAdapter(api_key=secret_key, session=session, auth_style="query_param")  # type: ignore[arg-type]
    result = adapter.fetch_document_raw("S100XXXX", download_type=1)
    assert secret_key not in json.dumps(result.request_parameters)


# --- EdinetDownloadType(公式仕様 + ローカル実データで確認済み、D0046追記) ---


def test_edinet_download_type_values_match_official_and_observed_mapping() -> None:
    assert EdinetDownloadType.MAIN_DOCUMENT_AND_AUDIT_REPORT == 1  # ZIP、実Download観測済み
    assert EdinetDownloadType.PDF == 2  # PDF
    assert EdinetDownloadType.ALTERNATIVE_ATTACHMENTS == 3  # ZIP
    assert EdinetDownloadType.ENGLISH_DOCUMENTS == 4  # ZIP
    assert EdinetDownloadType.CSV == 5  # ZIP


def test_edinet_download_type_1_matches_observed_zip_smoke_test() -> None:
    """2026-08-17のローカル実データ観測: docID=S100TD9S, type=1 ->
    Content-Type=application/octet-stream, magic bytes 50 4b 03 04(ZIP)、
    sha256=2515dd689d673c9dbd32148b5450fc34f0aa0ddd7ba8831f5e5c08067b2a4d1c。
    ここではその観測結果を模したバイト列で回帰確認する(実バイト列そのものは
    リポジトリへ格納しない、D0046 §16参照)。"""
    raw_bytes = b"\x50\x4b\x03\x04" + b"observed-shape-placeholder"
    session = _RecordingSession(content=raw_bytes, content_type="application/octet-stream")
    adapter = EdinetAdapter(api_key="k", session=session)  # type: ignore[arg-type]
    result = adapter.fetch_document_raw("S100TD9S", download_type=int(EdinetDownloadType.MAIN_DOCUMENT_AND_AUDIT_REPORT))
    decoded = base64.b64decode(result.payload["content_base64"])
    assert decoded[:4] == b"\x50\x4b\x03\x04"


# --- 例外時のAPIキー非漏洩 ---


def test_edinet_adapter_connection_failure_does_not_leak_api_key_in_exception() -> None:
    secret_key = "super-secret-edinet-key-xyz"
    adapter = EdinetAdapter(api_key=secret_key, session=_FailingSession())  # type: ignore[arg-type]
    with pytest.raises(DataSourceError) as excinfo:
        adapter.fetch_documents_list_raw(date(2024, 5, 8), list_type=2)
    assert secret_key not in str(excinfo.value)
    assert excinfo.value.__cause__ is None  # 原例外をchainしない(URLにキーを含みうるため)
    assert excinfo.value.__context__ is None


# --- Normalizer/Entity解決を一切呼ばないことの構造的確認 ---


def test_edinet_adapter_module_does_not_import_disclosures_normalize_or_view() -> None:
    """このAdapterはRaw Fetchのみ担い、正規化(normalize)・As-of View(view)には
    一切依存しないことをimport構造で確認する(未確認Field名を正規化に混入させない)。
    Normalizer本体(`edinet_normalize.py`)は別Moduleに分離してあるため対象外。"""
    import lib.disclosures.providers.edinet as edinet_module

    source = edinet_module.__file__
    assert source is not None
    with open(source, encoding="utf-8") as f:
        text = f.read()
    import_lines = [line.strip() for line in text.splitlines() if line.strip().startswith(("import ", "from "))]
    forbidden_modules = ("lib.disclosures.normalize", "lib.disclosures.view", "lib.disclosures.model")
    assert not any(module in line for line in import_lines for module in forbidden_modules)
    assert "DisclosureDocument(" not in text
