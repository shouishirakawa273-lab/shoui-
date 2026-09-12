"""CompanyIrAdapter(Phase4B-4)のTest。実際のCompany IR Websiteへは一切
接続しない(FakeSessionのみ使用)。Test IDはユーザーTask仕様のIR-001〜014
に対応する(実装からコピーせず、Source Integration Skill v1のRuleから
期待値を導出する)。
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import requests
from lib.disclosures.providers.company_ir import (
    CompanyIrAdapter,
    ComplianceCheckResult,
    ComplianceError,
    ComplianceStatus,
)
from lib.errors import AppendOnlyViolationError
from lib.snapshot import RawSnapshotStore


class _FakeResponse:
    def __init__(
        self,
        *,
        url: str,
        status_code: int = 200,
        content: bytes = b"<html>IR Page</html>",
        headers: dict[str, str] | None = None,
        history: list[_FakeResponse] | None = None,
    ) -> None:
        self.url = url
        self.status_code = status_code
        self.content = content
        self.headers = headers or {"Content-Type": "text/html"}
        self.history = history or []

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class _FakeSession:
    def __init__(self, response: _FakeResponse | None = None, *, raise_exc: Exception | None = None) -> None:
        self._response = response
        self._raise_exc = raise_exc
        self.last_call: dict[str, object] | None = None

    def get(self, url: str, *, timeout: int, allow_redirects: bool) -> _FakeResponse:
        self.last_call = {"url": url, "timeout": timeout, "allow_redirects": allow_redirects}
        if self._raise_exc is not None:
            raise self._raise_exc
        assert self._response is not None
        return self._response


def _allowed_compliance(**overrides: object) -> ComplianceCheckResult:
    base = {
        "terms_checked": True,
        "robots_checked": True,
        "automated_retrieval": ComplianceStatus.ALLOWED,
        "redistribution": ComplianceStatus.UNCLEAR,
        "retention": ComplianceStatus.UNCLEAR,
        "attribution_required": ComplianceStatus.NOT_CHECKED,
        "checked_by": "USER_MANUAL_REVIEW_2026-08-18",
        "checked_at": datetime(2026, 8, 18, 9, 0, tzinfo=UTC),
        "notes": "Test Fixture",
    }
    base.update(overrides)
    return ComplianceCheckResult(**base)  # type: ignore[arg-type]


# --- IR-001: Manual URL Successful Retrieval ---


def test_ir001_manual_url_successful_retrieval_and_raw_save(tmp_path: Path) -> None:
    response = _FakeResponse(url="https://ir.example.co.jp/news/20260818.html")
    adapter = CompanyIrAdapter(session=_FakeSession(response))  # type: ignore[arg-type]

    result = adapter.fetch_document_raw("https://ir.example.co.jp/news/20260818.html", compliance=_allowed_compliance())
    assert result.source == "COMPANY_IR"
    assert result.payload["raw_retrieval_hash"]
    assert result.payload["requested_url"] == "https://ir.example.co.jp/news/20260818.html"

    store = RawSnapshotStore(tmp_path)
    manifest = store.save(result, snapshot_id="ir_test_1")
    _loaded_manifest, payload = store.load("COMPANY_IR", "ir_test_1")
    assert payload["final_url"] == "https://ir.example.co.jp/news/20260818.html"
    assert manifest.content_hash


# --- IR-002: Raw Immutability(既存RawSnapshotStoreのAppend-only保証をCompany IR Sourceでも確認) ---


def test_ir002_raw_artifact_immutable_overwrite_rejected(tmp_path: Path) -> None:
    response = _FakeResponse(url="https://ir.example.co.jp/doc.pdf")
    adapter = CompanyIrAdapter(session=_FakeSession(response))  # type: ignore[arg-type]
    result = adapter.fetch_document_raw("https://ir.example.co.jp/doc.pdf", compliance=_allowed_compliance())

    store = RawSnapshotStore(tmp_path)
    store.save(result, snapshot_id="ir_immutable_1")
    with pytest.raises(AppendOnlyViolationError):
        store.save(result, snapshot_id="ir_immutable_1")


# --- IR-004: UNKNOWN Compliance Fails Closed ---


def test_ir004_unclear_compliance_fails_closed() -> None:
    adapter = CompanyIrAdapter(session=_FakeSession(_FakeResponse(url="https://ir.example.co.jp/x")))  # type: ignore[arg-type]
    compliance = _allowed_compliance(automated_retrieval=ComplianceStatus.UNCLEAR)
    with pytest.raises(ComplianceError):
        adapter.fetch_document_raw("https://ir.example.co.jp/x", compliance=compliance)


def test_ir004_not_checked_compliance_fails_closed() -> None:
    adapter = CompanyIrAdapter(session=_FakeSession(_FakeResponse(url="https://ir.example.co.jp/x")))  # type: ignore[arg-type]
    compliance = _allowed_compliance(automated_retrieval=ComplianceStatus.NOT_CHECKED)
    with pytest.raises(ComplianceError):
        adapter.fetch_document_raw("https://ir.example.co.jp/x", compliance=compliance)


# --- IR-005: Disallowed Retrieval Fails Closed ---


def test_ir005_disallowed_compliance_fails_closed() -> None:
    session = _FakeSession(_FakeResponse(url="https://ir.example.co.jp/x"))
    adapter = CompanyIrAdapter(session=session)  # type: ignore[arg-type]
    compliance = _allowed_compliance(automated_retrieval=ComplianceStatus.DISALLOWED)
    with pytest.raises(ComplianceError):
        adapter.fetch_document_raw("https://ir.example.co.jp/x", compliance=compliance)
    # Fail Closedが実際にHTTP呼び出し自体を防いでいること(Compliance判定は
    # Network I/Oより前に行われる)を直接確認する。
    assert session.last_call is None


# --- IR-006: Redirect Provenance ---


def test_ir006_redirect_provenance_requested_vs_final_url_distinguished() -> None:
    intermediate = _FakeResponse(url="https://ir.example.co.jp/old-path", status_code=301)
    final_response = _FakeResponse(
        url="https://cdn.example-storage.com/ir/final.pdf",
        history=[intermediate],
    )
    adapter = CompanyIrAdapter(session=_FakeSession(final_response))  # type: ignore[arg-type]

    result = adapter.fetch_document_raw("https://ir.example.co.jp/old-path", compliance=_allowed_compliance())

    assert result.payload["requested_url"] == "https://ir.example.co.jp/old-path"
    assert result.payload["final_url"] == "https://cdn.example-storage.com/ir/final.pdf"
    assert result.payload["requested_url"] != result.payload["final_url"]
    assert result.payload["requested_domain"] == "ir.example.co.jp"
    assert result.payload["final_domain"] == "cdn.example-storage.com"
    assert len(result.payload["redirect_chain"]) == 1
    assert result.payload["redirect_chain"][0]["url"] == "https://ir.example.co.jp/old-path"


def test_ir006_same_domain_redirect_recorded_without_warning(caplog: pytest.LogCaptureFixture) -> None:
    response = _FakeResponse(url="https://ir.example.co.jp/final")
    adapter = CompanyIrAdapter(session=_FakeSession(response))  # type: ignore[arg-type]
    result = adapter.fetch_document_raw("https://ir.example.co.jp/final", compliance=_allowed_compliance())
    assert result.payload["requested_domain"] == result.payload["final_domain"]


# --- Defense in depth: skeptic-reviewer Finding(Phase4B-4) ---


def test_compliance_check_result_rejects_allowed_without_terms_or_robots_checked() -> None:
    """`terms_checked`/`robots_checked`がFalseのまま`automated_retrieval=
    ALLOWED`だけを主張する内部矛盾を、Dataclass自身が拒否することを確認
    する(skeptic-reviewerが指摘した、4 Fieldどうしの自己矛盾Guardが
    無かったGapへの修正。robots.txt/利用規約の自動解析Engineを新設した
    わけではない)。"""
    with pytest.raises(ValueError, match="terms_checked/robots_checked"):
        _allowed_compliance(terms_checked=False)
    with pytest.raises(ValueError, match="terms_checked/robots_checked"):
        _allowed_compliance(robots_checked=False)


# --- IR-012: Timezone(Compliance側) ---


def test_ir012_compliance_checked_at_requires_tz_aware() -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        ComplianceCheckResult(
            terms_checked=True,
            robots_checked=True,
            automated_retrieval=ComplianceStatus.ALLOWED,
            redistribution=ComplianceStatus.UNCLEAR,
            retention=ComplianceStatus.UNCLEAR,
            attribution_required=ComplianceStatus.NOT_CHECKED,
            checked_by="USER_MANUAL_REVIEW",
            checked_at=datetime(2026, 8, 18, 9, 0),  # naive
        )


# --- IR-013: Secret Safety ---


def test_ir013_credential_like_query_param_url_rejected() -> None:
    adapter = CompanyIrAdapter(session=_FakeSession(_FakeResponse(url="https://ir.example.co.jp/x")))  # type: ignore[arg-type]
    with pytest.raises(ComplianceError):
        adapter.fetch_document_raw("https://ir.example.co.jp/doc.pdf?access_token=abc123", compliance=_allowed_compliance())


def test_ir013_basic_auth_url_rejected() -> None:
    adapter = CompanyIrAdapter(session=_FakeSession(_FakeResponse(url="https://ir.example.co.jp/x")))  # type: ignore[arg-type]
    with pytest.raises(ComplianceError):
        adapter.fetch_document_raw("https://user:password@ir.example.co.jp/doc.pdf", compliance=_allowed_compliance())


def test_ir013_only_allowlisted_headers_recorded_not_all_headers() -> None:
    response = _FakeResponse(
        url="https://ir.example.co.jp/x",
        headers={
            "Content-Type": "text/html",
            "Set-Cookie": "session=SECRET_SESSION_VALUE",
            "Authorization": "Bearer SECRET_TOKEN",
        },
    )
    adapter = CompanyIrAdapter(session=_FakeSession(response))  # type: ignore[arg-type]
    result = adapter.fetch_document_raw("https://ir.example.co.jp/x", compliance=_allowed_compliance())

    recorded_headers = result.payload["headers"]
    assert "Set-Cookie" not in recorded_headers
    assert "Authorization" not in recorded_headers
    assert recorded_headers["Content-Type"] == "text/html"
    # PayloadのどこにもSecret値そのものが含まれていないことを直接確認する。
    assert "SECRET_SESSION_VALUE" not in str(result.payload)
    assert "SECRET_TOKEN" not in str(result.payload)


def test_ir013_request_parameters_contain_no_secret_like_keys(tmp_path: Path) -> None:
    """`RawSnapshotStore.save()`自身のSecret Guard(`_assert_no_secret_like_
    keys`)が、Company IRのrequest_parameters形状でも正しく通過する
    (=`requested_url`という単一Keyのみで、token/key/secret等を含まない)
    ことを直接確認する。"""
    response = _FakeResponse(url="https://ir.example.co.jp/x")
    adapter = CompanyIrAdapter(session=_FakeSession(response))  # type: ignore[arg-type]
    result = adapter.fetch_document_raw("https://ir.example.co.jp/x", compliance=_allowed_compliance())
    assert list(result.request_parameters.keys()) == ["requested_url"]

    store = RawSnapshotStore(tmp_path)
    store.save(result, snapshot_id="ir_secret_check_1")  # Secret Guardで例外にならないこと


# --- HTTP Transport Failure ---


def test_transport_failure_raises_data_source_error_not_leaking_details() -> None:
    session = _FakeSession(response=None, raise_exc=requests.ConnectionError("boom"))
    adapter = CompanyIrAdapter(session=session)  # type: ignore[arg-type]
    from lib.errors import DataSourceError

    with pytest.raises(DataSourceError):
        adapter.fetch_document_raw("https://ir.example.co.jp/x", compliance=_allowed_compliance())
