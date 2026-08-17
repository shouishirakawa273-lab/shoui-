"""Phase4B-3(D0048): `lib.disclosures.providers.tdnet.TdnetAdapter`のテスト。

`TdnetAdapter`はRaw HTTP Fetchのみを提供し(Field-level Normalizationは行わない)、
実ネットワーク呼び出しは一切行わない(`requests.Session`をMockする、ルートCLAUDE.md
「外部API呼び出しは...テストでモックする」に従う)。

このAdapterが前提とするEndpoint/Field名は`EXTERNAL_OFFICIAL_SPEC_VERIFICATION`
(ユーザーが別のWeb-access環境から確認したと申告した内容)に基づく。Claude自身が
このSession内でFetchして確認したものではない(`TDNET_SOURCE_ONBOARDING.md`参照)。
"""

from __future__ import annotations

import json
from datetime import date

import pytest
import requests
from lib.disclosures.providers.tdnet import BASE_URL, TdnetAdapter, TdnetApiError
from lib.errors import DataSourceError

_SUCCESS_LIST_BODY = {
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
            "DiscItems": ["01", "02"],
            "Docs": {"pdf": "https://example.invalid/full.pdf"},
        }
    ],
    "cursor": "cursor-abc",
    "pagination_key": None,
}


class _RecordingSession:
    def __init__(self, json_body: object = None, *, status_code: int = 200, headers: dict[str, str] | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self._json_body = json_body if json_body is not None else _SUCCESS_LIST_BODY
        self._status_code = status_code
        self._headers = headers or {}

    def get(self, url: str, *, params: dict[str, object], headers: dict[str, str], timeout: int) -> object:
        self.calls.append({"url": url, "params": dict(params), "headers": dict(headers), "timeout": timeout})
        json_body = self._json_body
        outer_status_code = self._status_code
        outer_headers = self._headers

        class _Resp:
            status_code = outer_status_code
            headers = outer_headers

            def raise_for_status(self) -> None:
                if 400 <= outer_status_code < 600:
                    raise requests.HTTPError(f"HTTP {outer_status_code}")

            def json(self) -> object:
                if isinstance(json_body, Exception):
                    raise json_body
                return json_body

        return _Resp()


class _FailingSession:
    def get(self, *args: object, **kwargs: object) -> None:
        raise requests.exceptions.ConnectionError(f"failed to connect (params={kwargs.get('params')})")


class _Sequenced429ThenSuccessSession:
    """1回目は429、2回目は成功を返す(Retry-After Backoff確認用)。"""

    def __init__(self) -> None:
        self.call_count = 0

    def get(self, url: str, *, params: dict[str, object], headers: dict[str, str], timeout: int) -> object:
        self.call_count += 1
        is_first_call = self.call_count == 1
        body = _SUCCESS_LIST_BODY

        class _Resp:
            status_code = 429 if is_first_call else 200
            headers = {"Retry-After": "0.01"} if is_first_call else {}

            def raise_for_status(self) -> None:
                return None

            def json(self) -> object:
                return body

        return _Resp()


# --- 未設定時の挙動 ---


def test_tdnet_adapter_unconfigured_raises_data_source_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JQUANTS_API_KEY", raising=False)
    adapter = TdnetAdapter(api_key=None)
    assert adapter.configured is False
    with pytest.raises(DataSourceError, match="JQUANTS_API_KEY"):
        adapter.fetch_documents_list_raw(target_date=date(2026, 8, 17))


def test_tdnet_adapter_configured_true_when_key_present() -> None:
    adapter = TdnetAdapter(api_key="test-key")
    assert adapter.configured is True


# --- 認証(x-api-key、EXTERNAL_OFFICIAL_SPEC_VERIFICATION) ---


def test_tdnet_adapter_sends_x_api_key_header_only() -> None:
    session = _RecordingSession()
    adapter = TdnetAdapter(api_key="secret-key-abc", session=session)  # type: ignore[arg-type]
    result = adapter.fetch_documents_list_raw(target_date=date(2026, 8, 17))

    call = session.calls[0]
    assert call["headers"] == {"x-api-key": "secret-key-abc"}
    assert BASE_URL in str(call["url"])
    # Snapshotへ記録される側にはAPIキーが一切含まれない。
    assert "secret-key-abc" not in json.dumps(result.request_parameters)


# --- Documents List Query Validation(EXTERNAL_OFFICIAL_SPEC_VERIFICATION §3/§4) ---


def test_fetch_documents_list_raw_requires_date_or_code() -> None:
    adapter = TdnetAdapter(api_key="k", session=_RecordingSession())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="target_dateまたはcode"):
        adapter.fetch_documents_list_raw()


def test_fetch_documents_list_raw_rejects_both_date_and_code() -> None:
    adapter = TdnetAdapter(api_key="k", session=_RecordingSession())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="target_dateまたはcode"):
        adapter.fetch_documents_list_raw(target_date=date(2026, 8, 17), code="7203")


def test_fetch_documents_list_raw_rejects_cursor_and_pagination_key_together() -> None:
    adapter = TdnetAdapter(api_key="k", session=_RecordingSession())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="cursorとpagination_key"):
        adapter.fetch_documents_list_raw(target_date=date(2026, 8, 17), cursor="c1", pagination_key="p1")


def test_fetch_documents_list_raw_rejects_date_with_from_to() -> None:
    """target_date指定時にfrom/toを組み合わせる挙動は未確認のため許可しない
    (code指定時のみfrom/toの期間クエリが使える、EXTERNAL_OFFICIAL_SPEC_VERIFICATION §3)。"""
    adapter = TdnetAdapter(api_key="k", session=_RecordingSession())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="from_date/to_date"):
        adapter.fetch_documents_list_raw(target_date=date(2026, 8, 17), from_date=date(2026, 1, 1))


def test_fetch_documents_list_raw_with_date_sends_date_param_only() -> None:
    session = _RecordingSession()
    adapter = TdnetAdapter(api_key="k", session=session)  # type: ignore[arg-type]
    result = adapter.fetch_documents_list_raw(target_date=date(2026, 8, 17))

    assert result.request_parameters == {"date": "2026-08-17"}
    assert result.data_period == "2026-08-17"


def test_fetch_documents_list_raw_with_code_and_period_sends_from_to() -> None:
    session = _RecordingSession()
    adapter = TdnetAdapter(api_key="k", session=session)  # type: ignore[arg-type]
    result = adapter.fetch_documents_list_raw(code="7203", from_date=date(2026, 1, 1), to_date=date(2026, 6, 30))

    assert result.request_parameters == {"code": "7203", "from": "2026-01-01", "to": "2026-06-30"}
    assert "2026-01-01" in result.data_period
    assert "2026-06-30" in result.data_period


def test_fetch_documents_list_raw_with_code_only_notes_unconfirmed_coverage_window() -> None:
    session = _RecordingSession()
    adapter = TdnetAdapter(api_key="k", session=session)  # type: ignore[arg-type]
    result = adapter.fetch_documents_list_raw(code="7203")

    assert result.request_parameters == {"code": "7203"}
    assert "unconfirmed" in result.data_period


def test_fetch_documents_list_raw_passes_disc_items_as_opaque_param() -> None:
    session = _RecordingSession()
    adapter = TdnetAdapter(api_key="k", session=session)  # type: ignore[arg-type]
    adapter.fetch_documents_list_raw(target_date=date(2026, 8, 17), disc_items="01")

    assert session.calls[0]["params"]["discItems"] == "01"


def test_fetch_documents_list_raw_returns_raw_payload_untouched() -> None:
    session = _RecordingSession(json_body=_SUCCESS_LIST_BODY)
    adapter = TdnetAdapter(api_key="k", session=session)  # type: ignore[arg-type]
    result = adapter.fetch_documents_list_raw(target_date=date(2026, 8, 17))

    assert result.source == "TDNET"
    assert result.endpoint == "/v2/td/list"
    assert result.payload == _SUCCESS_LIST_BODY  # Normalizationしていない、生のまま


def test_fetch_documents_list_raw_non_dict_response_raises_error() -> None:
    session = _RecordingSession(json_body=["not", "a", "dict"])
    adapter = TdnetAdapter(api_key="k", session=session)  # type: ignore[arg-type]
    with pytest.raises(TdnetApiError, match="辞書構造"):
        adapter.fetch_documents_list_raw(target_date=date(2026, 8, 17))


def test_fetch_documents_list_raw_non_json_response_raises_data_source_error() -> None:
    session = _RecordingSession(json_body=ValueError("not json"))
    adapter = TdnetAdapter(api_key="k", session=session)  # type: ignore[arg-type]
    with pytest.raises(DataSourceError, match="JSON"):
        adapter.fetch_documents_list_raw(target_date=date(2026, 8, 17))


# --- /v2/td/files ---


def test_fetch_files_raw_requires_disc_no_and_sends_optional_docs() -> None:
    session = _RecordingSession(json_body={"discNo": "20260817001", "files": {"pdf": "https://example.invalid/x.pdf"}})
    adapter = TdnetAdapter(api_key="k", session=session)  # type: ignore[arg-type]
    result = adapter.fetch_files_raw("20260817001", docs="g")

    assert session.calls[0]["params"] == {"discNo": "20260817001", "docs": "g"}
    assert result.endpoint == "/v2/td/files"
    assert result.data_period == "20260817001"


def test_fetch_files_raw_without_docs_omits_param() -> None:
    session = _RecordingSession(json_body={"discNo": "20260817001"})
    adapter = TdnetAdapter(api_key="k", session=session)  # type: ignore[arg-type]
    adapter.fetch_files_raw("20260817001")
    assert "docs" not in session.calls[0]["params"]


# --- /v2/td/bulk ---


def test_fetch_bulk_raw_returns_metadata_only() -> None:
    session = _RecordingSession(json_body={"lastUpdated": "2026-08-17T10:00:00Z", "url": "https://example.invalid/bulk.csv.gz"})
    adapter = TdnetAdapter(api_key="k", session=session)  # type: ignore[arg-type]
    result = adapter.fetch_bulk_raw()

    assert result.endpoint == "/v2/td/bulk"
    assert result.request_parameters == {}
    assert result.payload["lastUpdated"] == "2026-08-17T10:00:00Z"


# --- Rate Limit / 429 Backoff ---


def test_request_retries_on_429_and_respects_retry_after() -> None:
    session = _Sequenced429ThenSuccessSession()
    adapter = TdnetAdapter(api_key="k", session=session)  # type: ignore[arg-type]
    result = adapter.fetch_documents_list_raw(target_date=date(2026, 8, 17))

    assert session.call_count == 2
    assert result.payload == _SUCCESS_LIST_BODY


def test_request_exhausts_429_retries_and_raises() -> None:
    class _AlwaysRateLimitedSession:
        def get(self, *args: object, **kwargs: object) -> object:
            class _Resp:
                status_code = 429
                headers = {"Retry-After": "0.001"}

                def raise_for_status(self) -> None:
                    return None

                def json(self) -> object:
                    return {}

            return _Resp()

    adapter = TdnetAdapter(api_key="k", session=_AlwaysRateLimitedSession())  # type: ignore[arg-type]
    with pytest.raises(TdnetApiError, match="429"):
        adapter.fetch_documents_list_raw(target_date=date(2026, 8, 17))


def test_http_error_status_raises_data_source_error() -> None:
    session = _RecordingSession(json_body={"error": "forbidden"}, status_code=403)
    adapter = TdnetAdapter(api_key="k", session=session)  # type: ignore[arg-type]
    with pytest.raises(DataSourceError, match="403"):
        adapter.fetch_documents_list_raw(target_date=date(2026, 8, 17))


# --- 例外時のAPIキー非漏洩 ---


def test_tdnet_adapter_connection_failure_does_not_leak_api_key_in_exception() -> None:
    secret_key = "super-secret-tdnet-key-xyz"
    adapter = TdnetAdapter(api_key=secret_key, session=_FailingSession())  # type: ignore[arg-type]
    with pytest.raises(DataSourceError) as excinfo:
        adapter.fetch_documents_list_raw(target_date=date(2026, 8, 17))
    assert secret_key not in str(excinfo.value)
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__context__ is None


# --- Normalizer/Entity解決を一切呼ばないことの構造的確認 ---


def test_tdnet_adapter_module_does_not_import_disclosures_normalize_or_view() -> None:
    """このAdapterはRaw Fetchのみ担い、正規化(normalize)・As-of View(view)には
    一切依存しないことをimport構造で確認する(未確認Field名を正規化に混入させない)。
    Normalizer本体(`tdnet_normalize.py`)は別Moduleに分離してあるため対象外。"""
    import lib.disclosures.providers.tdnet as tdnet_module

    source = tdnet_module.__file__
    assert source is not None
    with open(source, encoding="utf-8") as f:
        text = f.read()
    import_lines = [line.strip() for line in text.splitlines() if line.strip().startswith(("import ", "from "))]
    forbidden_modules = ("lib.disclosures.normalize", "lib.disclosures.view", "lib.disclosures.model")
    assert not any(module in line for line in import_lines for module in forbidden_modules)
    assert "DisclosureDocument(" not in text


def test_tdnet_adapter_never_constructs_document_relationship() -> None:
    """タスク上最重要の禁止事項(新DiscNoによる旧DiscNoのCORRECTS自動生成禁止)
    が、Adapter層でも構造的に守られていることを確認する。"""
    import lib.disclosures.providers.tdnet as tdnet_module

    source = tdnet_module.__file__
    assert source is not None
    with open(source, encoding="utf-8") as f:
        text = f.read()
    assert "DocumentRelationship" not in text
    assert "DuplicateRelationKind" not in text
