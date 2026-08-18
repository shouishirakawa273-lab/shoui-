"""Company IR(企業投資家向け広報サイト)への接続(Phase4B-4)。

**Manual / User-specified URL First(v1の基本方針)**: 全上場企業を巡回する
Crawlerは作らない。Sitemap全巡回・IR自動発見・Search Engine Crawling・
robots.txt/利用規約の回避はいずれも行わない(`.claude/skills/source-
integration/SKILL.md`のCommon Core Rule群に加え、このModule固有の
制約として明記する)。呼び出し側が個別に指定したURL 1件を取得するのみ。

## Compliance First(取得前の第一級要件)

「Web上で公開されている」= 「自動取得・保存・再配布してよい」ではない。
このModuleは、robots.txt/利用規約の**自動解析**(NLP的な自動判定)を
行わない — それ自体が新しい不確実な推測Engineになってしまうため。
代わりに、呼び出し側(通常は人間によるManual確認)が`ComplianceCheckResult`
を明示的に構築して渡すことを必須とし、`automated_retrieval`が`ALLOWED`
でなければ`fetch_document_raw()`はFetchを実行せず`ComplianceError`を
送出する(Fail Closed、UNCLEAR/DISALLOWED/NOT_CHECKEDいずれも拒否)。

## Source Identity

- Claimant / Issuer: 発行体企業そのもの(`entity_id`、Normalizer側で解決)。
- Publishing Website: 企業IR Website(このModuleでは`requested_url`/
  `final_url`のDomainとしてのみ記録、企業そのものと同一視しない)。
- Retrieval Source: 実際に取得したURL/HTTP Endpoint。
- Research System: このLab自身。

## PIT Semantics(重要、既存Source Integration Skill v1 PIT-*を継承)

`market_public_at`は呼び出し側が明示的に確認済みの値を渡した場合のみ
設定する(HTML本文からの自動抽出は行わない、日付のみで時刻が無い場合は
時刻を推測しない)。`provider_available_at`はこのAdapter/Normalizerでは
一切設定しない(HTTP `Last-Modified`ヘッダを`provider_available_at`へ
Mappingすることを明示的に禁止する — Website運用者のCache/CDN都合による
Last-Modifiedと、実際にこのLabのRetrieval Systemが参照可能になった時刻は
別物であり、確認できていない)。`retrieved_at`のみがPIT判定の直接基準
(Observed Safe Availability Timestamp)として使われる。
"""

from __future__ import annotations

import base64
import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests

from lib.data_sources.base import RawFetchResult
from lib.errors import DataSourceError

logger = logging.getLogger(__name__)

RESPONSE_SCHEMA_VERSION = "company_ir-v1(Manual URL First、実Company IR Siteへの疎通は未検証)"
SOURCE_ID = "COMPANY_IR"
_FETCH_ENDPOINT_LABEL = "COMPANY_IR_HTTP_GET"

# lib.snapshot._assert_no_secret_like_keysと同じ判定基準をURL Query
# Parameterへも適用する(Section19「API key/Session Cookie/Auth Token等を
# 保存・ログ出力しない」)。Signed/Authenticated URLを「公開Document URL」
# として誤って扱わないためのFail Closed Guard。
_FORBIDDEN_QUERY_KEY_SUBSTRINGS = ("token", "key", "secret", "password", "authorization", "credential")

# 記録するHTTP Response Headerは明示的なAllowlistのみ(Set-Cookie/
# Authorization等を含む全Header dictをそのまま保存しない、Section19)。
_RECORDED_HEADER_NAMES = ("Content-Type", "Content-Length", "ETag", "Last-Modified")


class ComplianceStatus(StrEnum):
    """Compliance確認の結果(項目ごとに個別に持つ、Section 6-1)。

    `NOT_CHECKED`/`UNCLEAR`のいずれも、Automated Retrievalを許可する
    根拠にはならない(`assert_retrieval_allowed()`参照)。"""

    ALLOWED = "ALLOWED"
    DISALLOWED = "DISALLOWED"
    UNCLEAR = "UNCLEAR"
    NOT_CHECKED = "NOT_CHECKED"


class ComplianceError(DataSourceError):
    """`automated_retrieval`が`ALLOWED`でないURLへFetchを試みた場合に送出する。"""


@dataclass(kw_only=True, frozen=True)
class ComplianceCheckResult:
    """1つのURL(またはDomain)についてのCompliance確認結果(Section 6-1)。

    このLab自身がrobots.txt/利用規約を自動解析して埋めるFieldではない
    (自動解析Engine自体を作らないという設計判断)。呼び出し側が確認した
    結果を明示的に渡す。`checked_by`は誰/何が確認したかを示す監査証跡
    (例: `"USER_MANUAL_REVIEW_2026-08-18"`)であり、`"AUTOMATED_NLP_
    JUDGMENT"`のような値をこのLab自身が生成することはない。
    """

    terms_checked: bool
    robots_checked: bool
    automated_retrieval: ComplianceStatus
    redistribution: ComplianceStatus
    retention: ComplianceStatus
    attribution_required: ComplianceStatus
    checked_by: str
    checked_at: datetime
    notes: str = ""

    def __post_init__(self) -> None:
        if self.checked_at.tzinfo is None:
            raise ValueError("checked_at はtz-awareである必要があります")


def assert_retrieval_allowed(compliance: ComplianceCheckResult) -> None:
    """Fail Closed Gate(Section 7): `automated_retrieval == ALLOWED`の
    場合のみ通過する。`UNCLEAR`/`DISALLOWED`/`NOT_CHECKED`はいずれも拒否する
    (「たぶん公開情報だから大丈夫」という楽観的判断をコード上で許さない)。
    """
    if compliance.automated_retrieval != ComplianceStatus.ALLOWED:
        raise ComplianceError(
            f"Automated Retrievalが許可されていません(automated_retrieval="
            f"{compliance.automated_retrieval.value})。Manual Reviewが必要です。"
        )


def _assert_url_has_no_credential_like_query_params(url: str) -> None:
    parsed = urlparse(url)
    if parsed.username or parsed.password:
        raise ComplianceError("URLにUser情報(Basic Auth形式)が含まれています。認証済みURLは扱いません。")
    query = parse_qs(parsed.query)
    for key in query:
        lowered = key.lower()
        if any(bad in lowered for bad in _FORBIDDEN_QUERY_KEY_SUBSTRINGS):
            raise ComplianceError(f"URLのQuery Parameter '{key}' が認証情報らしき名前です。Signed URLは扱いません。")


def _recorded_headers(headers: Any) -> dict[str, str | None]:
    return {name: headers.get(name) for name in _RECORDED_HEADER_NAMES}


def _redirect_chain(history: Any) -> list[dict[str, Any]]:
    return [{"url": getattr(r, "url", None), "status_code": getattr(r, "status_code", None)} for r in history]


def _domain(url: str) -> str:
    return urlparse(url).netloc


class CompanyIrAdapter:
    """任意のCompany IR URL 1件に対するRaw HTTP GET Client(Manual URL First)。

    Documents List・自動発見の類は一切提供しない(呼び出し側がURLを
    明示的に指定する設計、Section 3)。
    """

    def __init__(self, session: requests.Session | None = None) -> None:
        self._session = session or requests.Session()

    def fetch_document_raw(self, url: str, *, compliance: ComplianceCheckResult) -> RawFetchResult:
        """指定URLをHTTP GETで取得する。

        取得前に`assert_retrieval_allowed(compliance)`でFail Closed判定を
        行う。Redirectは追跡するが、`final_url`のDomainが`url`のDomainと
        異なる場合は警告Logを残す(Blockはしない、Section 10「少なくとも
        記録または警告」)。Content-Typeによる成功/失敗判定は行わない
        (HTML/PDF/その他明確なDocumentのいずれもv1の対象、Section 9)。

        Response Headerは明示的なAllowlist(Content-Type/Content-Length/
        ETag/Last-Modified)のみを記録する。Cookie/Authorization等は
        一切保存しない。`Last-Modified`はOpaqueな観測値として保持する
        のみで、このModule自身は`provider_available_at`等のPIT Fieldへは
        一切変換しない(変換は呼び出し側/Normalizerの責務外、そもそも
        存在しない経路として設計する)。
        """
        _assert_url_has_no_credential_like_query_params(url)
        assert_retrieval_allowed(compliance)

        requested_at = datetime.now(UTC)
        try:
            resp = self._session.get(url, timeout=30, allow_redirects=True)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise DataSourceError(f"Company IR Documentの取得に失敗しました({type(exc).__name__})") from None
        retrieved_at = datetime.now(UTC)

        final_url = resp.url
        requested_domain = _domain(url)
        final_domain = _domain(final_url)
        if requested_domain != final_domain:
            logger.warning(
                "company_ir: Redirectにより異なるDomainへ到達しました(requested_domain=%s, final_domain=%s, url=%s)",
                requested_domain,
                final_domain,
                url,
            )

        raw_bytes = resp.content
        payload = {
            "requested_url": url,
            "final_url": final_url,
            "redirect_chain": _redirect_chain(resp.history),
            "requested_domain": requested_domain,
            "final_domain": final_domain,
            "requested_at": requested_at.isoformat(),
            "http_status": resp.status_code,
            "headers": _recorded_headers(resp.headers),
            "content_base64": base64.b64encode(raw_bytes).decode("ascii"),
            "content_length_observed": len(raw_bytes),
            "raw_retrieval_hash": hashlib.sha256(raw_bytes).hexdigest(),
            "compliance": {
                "terms_checked": compliance.terms_checked,
                "robots_checked": compliance.robots_checked,
                "automated_retrieval": compliance.automated_retrieval.value,
                "redistribution": compliance.redistribution.value,
                "retention": compliance.retention.value,
                "attribution_required": compliance.attribution_required.value,
                "checked_by": compliance.checked_by,
                "checked_at": compliance.checked_at.isoformat(),
                "notes": compliance.notes,
            },
        }
        return RawFetchResult(
            source=SOURCE_ID,
            endpoint=_FETCH_ENDPOINT_LABEL,
            request_parameters={"requested_url": url},
            retrieved_at=retrieved_at,
            data_period=url,
            response_schema_version=RESPONSE_SCHEMA_VERSION,
            payload=payload,
        )


__all__ = [
    "CompanyIrAdapter",
    "ComplianceCheckResult",
    "ComplianceError",
    "ComplianceStatus",
    "SOURCE_ID",
    "assert_retrieval_allowed",
]
