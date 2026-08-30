"""EDINET Type-1 ZIP Package正規化(Stage 3.18.2、D0101)。

**Core Principle(D0045/D0100/D0100.2から継続)**: このModuleは「Documentに
何と書かれているか」をStructuralに正規化するのみで、その内容の意味
(Claim抽出・Risk/Catalyst分類・EvidenceRelation付与)は一切行わない
(本文Semantic Extractionは将来Phaseへ意図的に据え置く、D0045と同じ境界)。
PIT(`market_public_at`/`provider_available_at`/Historical Eligibility)も
このModuleの責務外(D0100.2 §9参照、`DisclosureDocument`側で扱う)。

## D0100/D0100.2で実測済みの前提(このModuleはこれらをそのままCode化する)

- EDINET Type-1 ZIP(PublicDoc/AuditDoc)は`zipfile`でValidに開ける。
- `0000000_header_*_ixbrl.htm`・`NNNNNNN_honbun_*_ixbrl.htm`等は
  `xml.etree.ElementTree`でWell-formed XMLとしてParse可能(実7203
  半期報告書[S100UP32]・臨時報告書[S100TD9S]いずれも確認済み)。
- 本文Narrativeは`ix:nonNumeric`要素(Inline XBRL、`xmlns:ix=
  "http://www.xbrl.org/2008/inlineXBRL"`)内のMixed Contentとして
  存在する。
- `style="display:none"`・`ix:hidden`要素配下のTextは人間可読な本文
  ではない(実測: Header Cover Pageに存在)。
- 同一Taxonomy要素名が同一Member内に複数回出現しうる(実測: S100UP32の
  `AddressMajorShareholders`等、株主一覧の繰り返し)——`occurrence_index`
  によるDisambiguationが必須。
- 一貫したNormalization関数を全ての比較(Member全体Text・個々の
  TextBlock Text)へ同一に適用しない限り、Exact Substring Citationが
  壊れる(D0100で実際に自己再現したFalse Negativeが根拠)。

## Raw Identity(このModuleは再発明しない)

Canonical Raw Content Identityは既存の
`lib.disclosures.providers.edinet_zip.compute_canonical_zip_content_hash()`
をそのまま再利用する。このModule自身は別のHash Algorithmを持たない。
`raw_canonical_content_hash`(Raw Identity)と`normalizer_version`
(正規化Logic自体のVersion)は意図的に分離したFieldであり、正規化Logicの
Bugfix/改善はRaw Identityを変えない。
"""

from __future__ import annotations

import html
import io
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from enum import StrEnum

from lib.disclosures.providers.edinet_zip import compute_canonical_zip_content_hash

NORMALIZER_VERSION = "EDINET_TYPE1_NORMALIZER_V1"

_IX_NAMESPACE = "http://www.xbrl.org/2008/inlineXBRL"

# D0100 §13(正規化Rule 8): NFKCは既定で適用しない。全角見出し
# (「１【提出理由】」等)・全角数字はSourceの構造的な意味を持つため、
# 半角へ勝手に畳み込まない。
_WHITESPACE_RE = re.compile(r"\s+")

# D0101 §7: 空/ほぼ空のFactを無視するための、明示的なConstant(暗黙の
# Globalな短文除外はしない)。実測(D0100.2、S100UP32)で意味のある本文
# ——`jpcrp_cor:BusinessRisksTextBlock`(正規化後63文字、「重要な変更は
# ありません」という短いが実質的な開示)——が63文字だったため、閾値は
# 「完全に空(0文字)」のみを除外する最小値に留める。
_MIN_TEXT_BLOCK_LENGTH = 1

# D0101 §12: Narrative正規化の対象とするMember種別(人間可読なInline XBRL
# XHTMLのみ)。xsd/linkbase/raw xbrl instance/manifestはNarrative化しない
# (D0100.2で実際に観測した通り、これらはTaxonomy定義・Fact値そのもの
# であり、本文ではない)。
_NARRATIVE_CONTENT_TYPES = frozenset({"HEADER", "BODY", "AUDIT"})

# D0101 §11(Linkbase Suffix): edinet_zip.pyの分類方針(D0046)と同じ考え方
# だが、このModule自身は別の分類Tableを持つ(edinet_zip.pyのCategorize
# Helperを直接importして共有すると、Canonical Hash計算という別責務と
# 密結合してしまうため、意図的に独立させている)。
_LINKBASE_SUFFIXES = ("_pre.xml", "_lab.xml", "_lab-en.xml", "_def.xml", "_cal.xml")


class DisclosureNormalizationError(ValueError):
    """EDINET Package自体がInvalidで正規化できない場合に送出する
    (Invalid ZIP・Malformed XML/XHTML Member・Decode不能等)。`ValueError`の
    Subclassであり、既存Code(`lib.disclosures.model`等)の`__post_init__`
    Validationと同じ「構造的に不正な入力はValueErrorで拒否する」方針を
    踏襲する。"""


class MemberContentType(StrEnum):
    """EDINET Type-1 ZIP Member 1件の種別(Member Path/拡張子から決定論的に
    分類する、D0101 §4)。完全なDocument Layout Ontologyは作らない。"""

    HEADER = "HEADER"
    BODY = "BODY"
    AUDIT = "AUDIT"
    XBRL_INSTANCE = "XBRL_INSTANCE"
    SCHEMA = "SCHEMA"
    LINKBASE = "LINKBASE"
    MANIFEST = "MANIFEST"
    OTHER = "OTHER"


@dataclass(kw_only=True, frozen=True)
class NormalizedTextBlock:
    """`ix:nonNumeric`要素1件から抽出した正規化済みNarrative Fact。

    `normalized_text`は、この要素が属する`NormalizedDisclosureMember.
    normalized_text`と**同一のNormalization関数**で生成されている必要が
    あり、`char_start`/`char_end`はそのMember Text内での正確な位置を
    指す(D0101 §9 Exact Quote Invariant、`NormalizedDisclosureMember.
    __post_init__`で強制検証する)。"""

    taxonomy_element_name: str
    occurrence_index: int
    normalized_text: str
    char_start: int
    char_end: int

    def __post_init__(self) -> None:
        if not self.taxonomy_element_name:
            raise ValueError("taxonomy_element_name は空にできません")
        if self.occurrence_index < 0:
            raise ValueError(f"{self.taxonomy_element_name}: occurrence_index は0以上である必要があります")
        if self.char_start < 0 or self.char_end < self.char_start:
            raise ValueError(f"{self.taxonomy_element_name}: char_start/char_end が不正です")
        if len(self.normalized_text) != (self.char_end - self.char_start):
            raise ValueError(f"{self.taxonomy_element_name}: normalized_text の長さがchar_start/char_endと整合しません")


@dataclass(kw_only=True, frozen=True)
class NormalizedDisclosureMember:
    """EDINET Package内、1 Member(1 File)の正規化済みContent。

    `text_blocks`はDocument Order(ZIP出現順ではなく、XML Tree内でのText
    出現順)で保持する。Exact Quote Invariant(D0101 §9)をConstructor時点
    (`__post_init__`)で強制する——`NormalizeEdinetType1Zip()`経由以外で
    直接構築された場合も同じ検証が働く。"""

    member_path: str
    content_type: MemberContentType
    normalized_text: str
    text_blocks: tuple[NormalizedTextBlock, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.member_path:
            raise ValueError("member_path は空にできません")
        for block in self.text_blocks:
            if block.char_end > len(self.normalized_text):
                raise ValueError(
                    f"{self.member_path}: TextBlock {block.taxonomy_element_name!r}"
                    f"(occurrence={block.occurrence_index}) のchar_endがnormalized_textの範囲を超えています"
                )
            actual = self.normalized_text[block.char_start : block.char_end]
            if actual != block.normalized_text:
                raise ValueError(
                    f"{self.member_path}: TextBlock {block.taxonomy_element_name!r}"
                    f"(occurrence={block.occurrence_index}) がExact Quote Invariantに違反しています"
                    "(member.normalized_text[char_start:char_end] != block.normalized_text)"
                )


@dataclass(kw_only=True, frozen=True)
class NormalizedDisclosureDocument:
    """EDINET Type-1 ZIP Package 1件全体の正規化結果。

    `raw_canonical_content_hash`は既存`compute_canonical_zip_content_
    hash()`の出力をそのまま保持する(Raw Identity)。`normalizer_version`
    はこのModule自身のVersion(正規化Logic)であり、Raw Identityとは独立に
    変化しうる(D0101 §11)。"""

    document_id: str
    raw_canonical_content_hash: str
    normalizer_version: str = NORMALIZER_VERSION
    members: tuple[NormalizedDisclosureMember, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.document_id:
            raise ValueError("document_id は空にできません")
        if not self.raw_canonical_content_hash:
            raise ValueError("raw_canonical_content_hash は空にできません")


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _namespace(tag: str) -> str | None:
    return tag[1:].split("}", 1)[0] if tag.startswith("{") else None


def _is_hidden_element(elem: ET.Element) -> bool:
    """D0101 §6: `ix:hidden`要素自身、または`style`属性に`display:none`
    (大小文字非依存)を含む要素をHiddenと判定する。CSS Engineの挙動を
    模倣しようとはしない(D0100/D0100.2で実際に観測された2つの具体的な
    Mechanismのみをv1でSupportする)。"""
    if _namespace(elem.tag) == _IX_NAMESPACE and _local_name(elem.tag) == "hidden":
        return True
    style = elem.get("style")
    if style and re.search(r"display\s*:\s*none", style, re.IGNORECASE):
        return True
    return False


def _normalize_joined_text(joined: str) -> str:
    """D0101 §5のNormalization Ruleを実装する唯一の関数。Member全体Text・
    個々のTextBlock Textいずれもこの関数だけを通す(D0100で実際に発生した
    「2つの異なるStrip方式を混在させるとExact Substring Matchが壊れる」
    という自己再現Bugを、単一関数への集約で構造的に防ぐ)。"""
    decoded = html.unescape(joined)
    return _WHITESPACE_RE.sub(" ", decoded).strip()


@dataclass
class _WalkResult:
    tokens: list[str]
    # (elem, name属性値, token_start_idx, token_end_idx) のList。Document
    # Order(Text出現順)のまま保持する。
    facts: list[tuple[str, int, int]]


def _walk(elem: ET.Element, *, hidden: bool, inside_fact: bool, result: _WalkResult) -> None:
    """ElementTreeをDocument Order(`.text`→子要素→`.tail`)で再帰的に走査し、
    Hidden Subtree配下のTextを除外しつつToken Listへ集約する。同じ走査の
    中で、Hiddenでない・かつ他の`ix:nonNumeric`の内側にNestしていない
    `ix:nonNumeric`要素それぞれについて、そのSubtreeが占めるTokenの開始/
    終了Indexを記録する(Member全体Textと個々のTextBlock Textを同一の
    Token列から導出することで、Normalization関数の不一致によるExact
    Quote Invariant違反を構造的に防ぐ、D0101 §5/§9)。

    **Nested Factの扱い(D0101、S100UP32実データ検証で発見)**: `escape=
    "true"`の`ix:nonNumeric`(例: 半期報告書AuditDocの
    `jpcrp_cor:IndependentAuditorsReportConsolidatedTextBlock`)は、内側に
    別の`ix:nonNumeric`(監査法人名・公認会計士名等のFact)をNestして
    持つことが実際に確認されている。Nested Factを独立したTop-level
    TextBlockとして抽出すると、Postorder木走査によりInner Factが
    Outer Factより先に`facts`へ記録され、`search_from`の単調増加Searchが
    Outer Fact自身のOffset特定に失敗する(Outer FactはInner Factより
    前から開始するため)。したがって、既に他の`ix:nonNumeric`の内側にある
    `ix:nonNumeric`はTop-level TextBlockとしては抽出しない(そのText自体は
    Outer FactのNormalized Textへそのまま含まれ続けるため、情報は失われ
    ない)。"""
    is_hidden = hidden or _is_hidden_element(elem)
    is_nonnumeric = _namespace(elem.tag) == _IX_NAMESPACE and _local_name(elem.tag) == "nonNumeric"
    is_fact = is_nonnumeric and not is_hidden and not inside_fact
    fact_start = len(result.tokens) if is_fact else -1
    child_inside_fact = inside_fact or is_nonnumeric

    if not is_hidden and elem.text:
        result.tokens.append(elem.text)
    for child in elem:
        _walk(child, hidden=is_hidden, inside_fact=child_inside_fact, result=result)
        if not is_hidden and child.tail:
            result.tokens.append(child.tail)

    if is_fact:
        name = elem.get("name")
        if name:  # D0101 §7: name属性が無いFactは抽出対象外(Silent Skip、Document全体はFailさせない)
            result.facts.append((name, fact_start, len(result.tokens)))


def _extract_member_text_and_blocks(root: ET.Element) -> tuple[str, tuple[NormalizedTextBlock, ...]]:
    walk_result = _WalkResult(tokens=[], facts=[])
    _walk(root, hidden=False, inside_fact=False, result=walk_result)

    member_text = _normalize_joined_text(" ".join(walk_result.tokens))

    occurrence_counters: dict[str, int] = {}
    search_from = 0
    blocks: list[NormalizedTextBlock] = []
    for name, start_idx, end_idx in walk_result.facts:
        block_text = _normalize_joined_text(" ".join(walk_result.tokens[start_idx:end_idx]))
        if len(block_text) < _MIN_TEXT_BLOCK_LENGTH:
            continue

        pos = member_text.find(block_text, search_from)
        if pos == -1:
            # D0101 §8: Document Order Searchで見つからない場合はFail
            # Closed(架空のOffsetを作らない)。search_from以前の位置に
            # しか存在しない場合も含め、あえてFallbackしない。
            raise DisclosureNormalizationError(
                f"TextBlock {name!r} をMember正規化Text内でDocument Order通りに特定できませんでした"
                "(Exact Quote Invariantを満たすOffsetが構築できません)"
            )
        char_start = pos
        char_end = pos + len(block_text)
        search_from = char_end

        occurrence_index = occurrence_counters.get(name, 0)
        occurrence_counters[name] = occurrence_index + 1

        blocks.append(
            NormalizedTextBlock(
                taxonomy_element_name=name,
                occurrence_index=occurrence_index,
                normalized_text=block_text,
                char_start=char_start,
                char_end=char_end,
            )
        )

    return member_text, tuple(blocks)


def _classify_member(member_path: str) -> MemberContentType:
    """Member Path/拡張子のみからDeterministicに分類する(D0101 §4)。
    実測済みEDINET Package構造(`XBRL/PublicDoc/`・`XBRL/AuditDoc/`)を前提
    とするが、未知のPathでも例外にはせず`OTHER`へfail closedする。"""
    normalized_path = member_path.replace("\\", "/")
    filename = normalized_path.rsplit("/", 1)[-1]
    lower = filename.lower()
    is_audit_dir = "/auditdoc/" in normalized_path.lower()

    if lower.startswith("manifest_") and lower.endswith(".xml"):
        return MemberContentType.MANIFEST
    if lower.endswith((".htm", ".html", ".xhtml")):
        if "header" in lower:
            return MemberContentType.HEADER
        return MemberContentType.AUDIT if is_audit_dir else MemberContentType.BODY
    if lower.endswith(".xbrl"):
        return MemberContentType.XBRL_INSTANCE
    if lower.endswith(".xsd"):
        return MemberContentType.SCHEMA
    if lower.endswith(_LINKBASE_SUFFIXES):
        return MemberContentType.LINKBASE
    return MemberContentType.OTHER


def normalize_edinet_type1_zip(*, document_id: str, raw_zip_bytes: bytes) -> NormalizedDisclosureDocument:
    """EDINET Document Download(`download_type=1`)のRaw ZIP bytesから
    `NormalizedDisclosureDocument`を構築する(D0101)。

    Narrative正規化の対象は`HEADER`/`BODY`/`AUDIT`(人間可読なInline XBRL
    XHTML)のみ(D0101 §12)。`XBRL_INSTANCE`/`SCHEMA`/`LINKBASE`/
    `MANIFEST`のMemberはNarrative Text化せず、`members`にも含めない
    (誤ってProse Blockとして出力しない、D0101 §16-P)。

    Member順序はMember Path(POSIX区切りへ正規化した文字列)の辞書順で
    Deterministicに決定する(D0101 §13)。EDINET自身のManifest順序解析は
    行わない(Overengineeringを避ける、`manifest_PublicDoc.xml`の
    `<ixbrl>`列挙順と実測上一致するが、依存はしない)。

    PIT(`market_public_at`等)はこの関数の責務外であり、一切算出しない
    (D0101 §18)。SemanticClaim/EvidenceRecordもこの関数の出力範囲外
    (D0101 §19)。
    """
    if not document_id:
        raise DisclosureNormalizationError("document_id は空にできません")

    try:
        zf = zipfile.ZipFile(io.BytesIO(raw_zip_bytes))
    except zipfile.BadZipFile as exc:
        raise DisclosureNormalizationError(f"Invalid ZIP: {exc}") from exc

    bad_member = zf.testzip()
    if bad_member is not None:
        raise DisclosureNormalizationError(f"ZIP Member破損を検知しました: {bad_member}")

    canonical_hash = compute_canonical_zip_content_hash(raw_zip_bytes)
    if not canonical_hash:
        raise DisclosureNormalizationError("compute_canonical_zip_content_hash() が空の値を返しました")

    infos = sorted(
        (info for info in zf.infolist() if not info.is_dir()),
        key=lambda info: info.filename.replace("\\", "/"),
    )

    members: list[NormalizedDisclosureMember] = []
    for info in infos:
        content_type = _classify_member(info.filename)
        if content_type.value not in _NARRATIVE_CONTENT_TYPES:
            continue

        raw_member_bytes = zf.read(info)
        try:
            member_text_source = raw_member_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DisclosureNormalizationError(f"{info.filename}: UTF-8としてdecodeできません: {exc}") from exc

        try:
            root = ET.fromstring(member_text_source)
        except ET.ParseError as exc:
            raise DisclosureNormalizationError(f"{info.filename}: Well-formed XML/XHTMLとしてParseできません: {exc}") from exc

        normalized_text, text_blocks = _extract_member_text_and_blocks(root)
        members.append(
            NormalizedDisclosureMember(
                member_path=info.filename,
                content_type=content_type,
                normalized_text=normalized_text,
                text_blocks=text_blocks,
            )
        )

    return NormalizedDisclosureDocument(
        document_id=document_id,
        raw_canonical_content_hash=canonical_hash,
        normalizer_version=NORMALIZER_VERSION,
        members=tuple(members),
    )


__all__ = [
    "NORMALIZER_VERSION",
    "DisclosureNormalizationError",
    "MemberContentType",
    "NormalizedDisclosureDocument",
    "NormalizedDisclosureMember",
    "NormalizedTextBlock",
    "normalize_edinet_type1_zip",
]
