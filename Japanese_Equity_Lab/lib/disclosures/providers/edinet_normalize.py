"""EDINET Documents List Raw Payload -> `DisclosureDocument` + EDINET固有Metadata
(Phase4B-2、D0046追記: Local Real Data Validation結果の反映)。

**このModuleが対象とするField**は、2026-08-17のローカル実データ観測で実際に
出現を確認したFieldのみ(`docID`/`edinetCode`/`secCode`/`JCN`/`filerName`/
`fundCode`/`ordinanceCode`/`formCode`/`docTypeCode`/`periodStart`/
`periodEnd`/`submitDateTime`/`docDescription`/`issuerEdinetCode`/
`subjectEdinetCode`/`subsidiaryEdinetCode`/`currentReportReason`/
`parentDocID`/`opeDateTime`/`withdrawalStatus`/`docInfoEditStatus`/
`disclosureStatus`/`xbrlFlag`/`pdfFlag`/`attachDocFlag`/`englishDocFlag`/
`csvFlag`/`legalStatus`/`seqNumber`)、および公式仕様で意味が確認できた
`processDateTime`(未観測だが仕様上存在するため`.get()`でBest-effort Parse)。
未知のFieldはRaw payload自体には残るが、このModuleでは一切参照しない。

## Provider-neutral Common Coreへは含めないEDINET固有情報

`DisclosureDocument`(`lib.disclosures.model`)はTDnet/EDINET/Company IRで
共有するProvider-neutralなSchemaであり、EDINET固有のField名を持ち込まない
(Phase4B-1の原則)。そのため、EDINET固有の確認済みFieldは
`EdinetDocumentMetadata`という別のDataclassへ保持し、`document_internal_id`
経由で対応する`DisclosureDocument`と関連付ける。

## このModuleが意図的にやらないこと(D0046参照)

- **`market_public_at`/`provider_available_at`への自動反映**:
  `submitDateTime`が「提出日時」であることは公式仕様で確認したが、それが
  Market Public(市場が実際に知りえた時刻)と一致する保証、あるいはEDINET
  APIでの反映Timing(Provider Available)を示す保証はいずれも未確認。両者を
  混同しないため、`DisclosureDocument.market_public_at`/`provider_
  available_at`はいずれも`None`/`AvailabilityBasis.UNKNOWN`のまま残し、
  `submitDateTime`のParse結果は`EdinetDocumentMetadata.submitted_at`という
  別名で保持する(EDINET固有のProvider Timestampとして扱う)。
- **`document_kind`のMapping**: `docTypeCode`の意味はLocal観測時に説明文
  (`docDescription`)から間接的に読み取れたに過ぎず、公式別紙1(Form Code
  List)そのものは未確認。Local Descriptionだけからの推測Mappingは
  Substring Heuristicと同じ危険性を持つため、このPhaseでは一切Mappingせず
  常に`DocumentKind.UNKNOWN`とする。`doc_type_code`はRaw値のまま
  `EdinetDocumentMetadata`へ保持し、将来公式Code Listが確認できた時点で
  明示的Mapping Tableを追加する。
- **`entity_id`の解決**: `secCode`はFiler(提出者)の証券コードであり、
  大量保有報告書等では`issuerEdinetCode`(発行会社)・`subjectEdinetCode`
  (公開買付対象)が別に存在する(Local実データで`filer != issuer`を確認
  済み)。単一の`entity_id`へ機械的に決め打ちすると誤ったRole混同を招くため、
  `DisclosureDocument.entity_id`は常に`None`のままとし、Role別の識別子は
  `EdinetDocumentMetadata`のfiler/issuer/subject/subsidiary各Fieldへ
  個別に保持する(正式なEntity Registry Mappingは将来Phase)。
- **Attachmentの実体化**: `xbrlFlag`等の5つのFlagは「その種類の添付が
  存在するかどうか」の確認済みSignalとして`bool | None`へ変換するが、
  `DisclosureAttachment`レコードは生成しない(Attachment Download
  Foundationは別Phase、スモークテストのみ実施済み)。
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import TypeVar
from zoneinfo import ZoneInfo

from lib.disclosures.model import NORMALIZER_VERSION, DisclosureDocument, DocumentKind
from lib.errors import DataSourceError
from lib.evidence.model import AvailabilityBasis

logger = logging.getLogger(__name__)

_JST = ZoneInfo("Asia/Tokyo")

EDINET_NORMALIZER_VERSION = f"{NORMALIZER_VERSION}+EDINET_V1"


class EdinetWithdrawalStatus(StrEnum):
    """`withdrawalStatus`(公式仕様確認済み)。Multi-state — Booleanへ落とさない。"""

    OTHER = "OTHER"  # "0" その他
    WITHDRAWAL_NOTICE = "WITHDRAWAL_NOTICE"  # "1" 取下書
    WITHDRAWN_DOCUMENT = "WITHDRAWN_DOCUMENT"  # "2" 取り下げられた書類
    UNKNOWN = "UNKNOWN"


class EdinetDocInfoEditStatus(StrEnum):
    """`docInfoEditStatus`(公式仕様確認済み)。"""

    OTHER = "OTHER"  # "0" その他
    EDITED_BY_FINANCE_BUREAU_STAFF = "EDITED_BY_FINANCE_BUREAU_STAFF"  # "1" 財務局職員が修正した情報
    EDITED_DOCUMENT = "EDITED_DOCUMENT"  # "2" 修正された書類
    UNKNOWN = "UNKNOWN"


class EdinetDisclosureStatus(StrEnum):
    """`disclosureStatus`(公式仕様確認済み)。"""

    OTHER = "OTHER"  # "0" その他
    NON_DISCLOSURE_START = "NON_DISCLOSURE_START"  # "1" 不開示開始情報
    NON_DISCLOSURE_ACTIVE = "NON_DISCLOSURE_ACTIVE"  # "2" 不開示中書類
    NON_DISCLOSURE_LIFTED = "NON_DISCLOSURE_LIFTED"  # "3" 不開示解除情報
    UNKNOWN = "UNKNOWN"


class EdinetLegalStatus(StrEnum):
    """`legalStatus`(公式仕様確認済み)。**Lifecycle Stateであり、Historical
    Availability(過去のある時点で実際に取得可能だったか)とは別概念**
    (D0046 §6/§7参照 — 現在このStatusが`UNDER_PUBLIC_VIEWING`であることは
    「今」縦覧中であることを示すのみで、過去の任意時点での可視性を保証しない)。
    """

    EXPIRED_OR_OTHER = "EXPIRED_OR_OTHER"  # "0" 閲覧期間満了等
    UNDER_PUBLIC_VIEWING = "UNDER_PUBLIC_VIEWING"  # "1" 縦覧中
    UNDER_EXTENDED_PERIOD = "UNDER_EXTENDED_PERIOD"  # "2" 延長期間中
    UNKNOWN = "UNKNOWN"


_WITHDRAWAL_STATUS_MAP: dict[str, EdinetWithdrawalStatus] = {
    "0": EdinetWithdrawalStatus.OTHER,
    "1": EdinetWithdrawalStatus.WITHDRAWAL_NOTICE,
    "2": EdinetWithdrawalStatus.WITHDRAWN_DOCUMENT,
}
_DOC_INFO_EDIT_STATUS_MAP: dict[str, EdinetDocInfoEditStatus] = {
    "0": EdinetDocInfoEditStatus.OTHER,
    "1": EdinetDocInfoEditStatus.EDITED_BY_FINANCE_BUREAU_STAFF,
    "2": EdinetDocInfoEditStatus.EDITED_DOCUMENT,
}
_DISCLOSURE_STATUS_MAP: dict[str, EdinetDisclosureStatus] = {
    "0": EdinetDisclosureStatus.OTHER,
    "1": EdinetDisclosureStatus.NON_DISCLOSURE_START,
    "2": EdinetDisclosureStatus.NON_DISCLOSURE_ACTIVE,
    "3": EdinetDisclosureStatus.NON_DISCLOSURE_LIFTED,
}
_LEGAL_STATUS_MAP: dict[str, EdinetLegalStatus] = {
    "0": EdinetLegalStatus.EXPIRED_OR_OTHER,
    "1": EdinetLegalStatus.UNDER_PUBLIC_VIEWING,
    "2": EdinetLegalStatus.UNDER_EXTENDED_PERIOD,
}
_KNOWN_FLAG_LITERALS: dict[str, bool] = {"0": False, "1": True}


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


_LifecycleStatusT = TypeVar(
    "_LifecycleStatusT", EdinetWithdrawalStatus, EdinetDocInfoEditStatus, EdinetDisclosureStatus, EdinetLegalStatus
)


def _parse_lifecycle_value(
    raw: object, value_map: Mapping[str, _LifecycleStatusT], unknown_member: _LifecycleStatusT, *, field_name: str
) -> _LifecycleStatusT | None:
    """`raw`が`None`(Fieldが欠損/null)の場合はそのまま`None`を返す
    (「値が無いこと」と「値はあるが認識できない('0'/'1'/'2'/'3'以外)こと」を
    区別する、D0046 §13 Null Semantics参照)。認識できない非null値は
    `unknown_member`(各EnumのUNKNOWN)へfail closedし、警告を残す
    (未知値をSilentに無視・0扱いしない)。"""
    if raw is None:
        return None
    raw_str = str(raw).strip()
    value = value_map.get(raw_str)
    if value is None:
        logger.warning("edinet: 未知の%s値 '%s' を検出しました。UNKNOWNへfail closedします", field_name, raw_str)
        return unknown_member
    return value


def _parse_withdrawal_status(raw: object) -> EdinetWithdrawalStatus | None:
    return _parse_lifecycle_value(raw, _WITHDRAWAL_STATUS_MAP, EdinetWithdrawalStatus.UNKNOWN, field_name="withdrawalStatus")


def _parse_doc_info_edit_status(raw: object) -> EdinetDocInfoEditStatus | None:
    return _parse_lifecycle_value(raw, _DOC_INFO_EDIT_STATUS_MAP, EdinetDocInfoEditStatus.UNKNOWN, field_name="docInfoEditStatus")


def _parse_disclosure_status(raw: object) -> EdinetDisclosureStatus | None:
    return _parse_lifecycle_value(raw, _DISCLOSURE_STATUS_MAP, EdinetDisclosureStatus.UNKNOWN, field_name="disclosureStatus")


def _parse_legal_status(raw: object) -> EdinetLegalStatus | None:
    return _parse_lifecycle_value(raw, _LEGAL_STATUS_MAP, EdinetLegalStatus.UNKNOWN, field_name="legalStatus")


def _parse_flag(raw: object, *, field_name: str) -> bool | None:
    """`"0"`/`"1"`という文字列Flagを明示的にParseする。Python truthiness
    (`bool("0")`が`True`になる罠、D0043/D0045と同じ既知パターン)を使わない。
    `None`(欠損)は`None`のまま返し、`False`へは変換しない。"""
    if raw is None:
        return None
    if isinstance(raw, bool):
        logger.warning("edinet: %sがbool型で渡されました(想定は文字列'0'/'1'): %r", field_name, raw)
        return raw
    if isinstance(raw, str):
        parsed = _KNOWN_FLAG_LITERALS.get(raw.strip())
        if parsed is not None:
            return parsed
        logger.warning("edinet: 未知の%s文字列値 '%s' を検出しました。Noneへfail closedします", field_name, raw)
        return None
    logger.warning("edinet: 未知の型の%s値 %r を検出しました。Noneへfail closedします", field_name, raw)
    return None


def _parse_date_or_none(raw: object, *, field_name: str) -> date | None:
    if raw is None:
        return None
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        logger.warning("edinet: 不正な%s値 '%s' を検出しました", field_name, raw)
        return None


def _parse_jst_datetime_or_none(raw: object, *, field_name: str) -> datetime | None:
    """公式仕様でJST(Japan time)であることは確認済みだが、正確な文字列Format
    (秒の有無等)は未確認のため複数Formatを試す。いずれも解釈できない場合は
    推測補完せず`None`へfail closedする。"""
    if raw is None:
        return None
    raw_str = str(raw).strip()
    if not raw_str:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            naive = datetime.strptime(raw_str, fmt)
        except ValueError:
            continue
        return naive.replace(tzinfo=_JST)
    logger.warning("edinet: %sの日時文字列を解釈できません: '%s'", field_name, raw_str)
    return None


@dataclass(kw_only=True, frozen=True)
class EdinetDocumentMetadata:
    """EDINET固有の確認済みField(Provider-neutral Common Coreへは含めない)。

    `document_internal_id`が対応する`DisclosureDocument.internal_document_id`
    への参照キー。
    """

    document_internal_id: str
    seq_number: str | None = None
    filer_edinet_code: str | None = None
    filer_sec_code: str | None = None
    filer_name: str | None = None
    jcn: str | None = None
    fund_code: str | None = None
    ordinance_code: str | None = None
    form_code: str | None = None
    doc_type_code: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    issuer_edinet_code: str | None = None
    subject_edinet_code: str | None = None
    subsidiary_edinet_code: str | None = None
    current_report_reason: str | None = None
    parent_doc_id: str | None = None
    submitted_at: datetime | None = None
    ope_at: datetime | None = None
    process_at: datetime | None = None
    withdrawal_status: EdinetWithdrawalStatus | None = None
    doc_info_edit_status: EdinetDocInfoEditStatus | None = None
    disclosure_status: EdinetDisclosureStatus | None = None
    legal_status: EdinetLegalStatus | None = None
    has_xbrl: bool | None = None
    has_pdf: bool | None = None
    has_attachments: bool | None = None
    has_english_docs: bool | None = None
    has_csv: bool | None = None


def _parse_row(
    row: Mapping[str, object], *, index: int, retrieved_at: datetime, raw_snapshot_ref: str | None
) -> tuple[DisclosureDocument, EdinetDocumentMetadata]:
    doc_id = _optional_str(row.get("docID"))
    internal_document_id = f"EDINET_{doc_id or 'UNKNOWN'}_{index}"
    doc_description = _optional_str(row.get("docDescription"))
    title = doc_description if doc_description else f"[EDINET docID={doc_id or 'UNKNOWN'}: docDescription unavailable]"

    document = DisclosureDocument(
        internal_document_id=internal_document_id,
        source_document_id=doc_id,
        entity_id=None,
        title=title,
        document_kind=DocumentKind.UNKNOWN,
        originating_source="EDINET",
        delivery_provider="EDINET",
        market_public_at=None,
        market_public_at_basis=AvailabilityBasis.UNKNOWN,
        provider_available_at=None,
        provider_available_at_basis=AvailabilityBasis.UNKNOWN,
        retrieved_at=retrieved_at,
        source_version=None,
        raw_snapshot_ref=raw_snapshot_ref,
        language=None,
        attachments=(),
        normalizer_version=EDINET_NORMALIZER_VERSION,
    )

    doc_metadata = EdinetDocumentMetadata(
        document_internal_id=internal_document_id,
        seq_number=_optional_str(row.get("seqNumber")),
        filer_edinet_code=_optional_str(row.get("edinetCode")),
        filer_sec_code=_optional_str(row.get("secCode")),
        filer_name=_optional_str(row.get("filerName")),
        jcn=_optional_str(row.get("JCN")),
        fund_code=_optional_str(row.get("fundCode")),
        ordinance_code=_optional_str(row.get("ordinanceCode")),
        form_code=_optional_str(row.get("formCode")),
        doc_type_code=_optional_str(row.get("docTypeCode")),
        period_start=_parse_date_or_none(row.get("periodStart"), field_name="periodStart"),
        period_end=_parse_date_or_none(row.get("periodEnd"), field_name="periodEnd"),
        issuer_edinet_code=_optional_str(row.get("issuerEdinetCode")),
        subject_edinet_code=_optional_str(row.get("subjectEdinetCode")),
        subsidiary_edinet_code=_optional_str(row.get("subsidiaryEdinetCode")),
        current_report_reason=_optional_str(row.get("currentReportReason")),
        parent_doc_id=_optional_str(row.get("parentDocID")),
        submitted_at=_parse_jst_datetime_or_none(row.get("submitDateTime"), field_name="submitDateTime"),
        ope_at=_parse_jst_datetime_or_none(row.get("opeDateTime"), field_name="opeDateTime"),
        process_at=_parse_jst_datetime_or_none(row.get("processDateTime"), field_name="processDateTime"),
        withdrawal_status=_parse_withdrawal_status(row.get("withdrawalStatus")),
        doc_info_edit_status=_parse_doc_info_edit_status(row.get("docInfoEditStatus")),
        disclosure_status=_parse_disclosure_status(row.get("disclosureStatus")),
        legal_status=_parse_legal_status(row.get("legalStatus")),
        has_xbrl=_parse_flag(row.get("xbrlFlag"), field_name="xbrlFlag"),
        has_pdf=_parse_flag(row.get("pdfFlag"), field_name="pdfFlag"),
        has_attachments=_parse_flag(row.get("attachDocFlag"), field_name="attachDocFlag"),
        has_english_docs=_parse_flag(row.get("englishDocFlag"), field_name="englishDocFlag"),
        has_csv=_parse_flag(row.get("csvFlag"), field_name="csvFlag"),
    )
    return document, doc_metadata


def parse_edinet_documents_list_payload(
    body: Mapping[str, object],
    *,
    retrieved_at: datetime,
    raw_snapshot_ref: str | None = None,
) -> list[tuple[DisclosureDocument, EdinetDocumentMetadata]]:
    """EDINET Documents List(``GET /documents.json``)の生Payload(既に
    `EdinetAdapter.fetch_documents_list_raw`が成功と判定したもの、または
    保存済みRaw Snapshotから読み込んだもの)を`DisclosureDocument`と
    `EdinetDocumentMetadata`のペアの列へ変換する。

    `metadata.status`を防御的に再検証する(Adapter層のGateとは独立、Raw
    Snapshotから直接呼ばれるケースを想定)。行単位のParse失敗は個別行を
    スキップせず、Fieldごとにfail closed値(None/UNKNOWN)を設定した上で
    Document自体は生成する(1行の不整合で全体のParseを止めない、Phase4B-1と
    同じ方針)。
    """
    metadata = body.get("metadata")
    if not isinstance(metadata, Mapping) or metadata.get("status") != "200":
        raise DataSourceError(f"EDINET Documents List payloadがmetadata.status='200'ではありません: {metadata!r}")
    results = body.get("results")
    if not isinstance(results, Sequence) or isinstance(results, (str, bytes)):
        raise DataSourceError("EDINET Documents List payloadに'results'リストがありません")

    parsed: list[tuple[DisclosureDocument, EdinetDocumentMetadata]] = []
    for index, row in enumerate(results):
        if not isinstance(row, Mapping):
            logger.warning("edinet: results[%d] が辞書形式ではありません。スキップします", index)
            continue
        parsed.append(_parse_row(row, index=index, retrieved_at=retrieved_at, raw_snapshot_ref=raw_snapshot_ref))
    return parsed


__all__ = [
    "EDINET_NORMALIZER_VERSION",
    "EdinetDisclosureStatus",
    "EdinetDocInfoEditStatus",
    "EdinetDocumentMetadata",
    "EdinetLegalStatus",
    "EdinetWithdrawalStatus",
    "parse_edinet_documents_list_payload",
]
