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

## Exact Quote Invariantの定義(D0101.1で明記)

「Exact Quote Invariant」とは、**Versionされた正規化済みDocument Text
に対する厳密一致**を意味し、Raw XML Bytesとのbyte-for-byte一致を意味
**しない**。Raw ZIPは常にAuthoritative Source(不変)のままであり、
`normalized_text`はそこからDeterministicに導出されるDerived
Representationである(空白畳み込み・Hidden Content除外を経ており、
Rawそのものではない)。この関数がRaw Sourceとのverbatim一致を主張する
ものではないことを、Semantic Extraction Layer(将来Phase)を含む
呼び出し側は前提とすること。

## Offset識別の方式(D0101.1、D0101-F01の修正)

D0101(初版)は`str.find(block_text, search_from)`による事後Substring
Searchで`char_start`/`char_end`を決定していた。これはTextの**内容一致**
は証明するが、**構造的同一性**は証明しない——例えば通常の地の文
(Ordinary Prose)に同じ文言が先行して存在する場合、Factが誤ってその
Prose側のOccurrenceへ結びつく可能性があった(Codex Adversarial Audit
Finding D0101-F01)。

D0101.1では、Offsetを**同じDOM走査(`_walk`)が生成するRaw Token列から
Structuralに導出**する方式へ変更した(`_normalize_with_offset_map()`)。
各Factの`char_start`/`char_end`は、そのFact自身のToken範囲がRaw結合
文字列上で占める区間を正規化Index空間へMapping変換した結果であり、
Member Text中の**どこか**を検索して一致箇所を探す操作は一切行わない。
これにより、`block.normalized_text`は`member.normalized_text[char_start:
char_end]`の**Sliceそのもの**として定義され、Exact Quote Invariantは
Searchの成否に関係なく構造的に常に成立する。

## Raw Identity(このModuleは再発明しない)

Canonical Raw Content Identityは既存の
`lib.disclosures.providers.edinet_zip.compute_canonical_zip_content_hash()`
をそのまま再利用する。このModule自身は別のHash Algorithmを持たない。
`raw_canonical_content_hash`(Raw Identity)と`normalizer_version`
(正規化Logic自体のVersion)は意図的に分離したFieldであり、正規化Logicの
Bugfix/改善はRaw Identityを変えない。
"""

from __future__ import annotations

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


def _normalize_with_offset_map(raw: str) -> tuple[str, list[int]]:
    """`raw`(DOM走査で得たRaw Token列を`" ".join()`したText)を、空白Run
    をASCII Space 1個へ畳み込み・先頭/末尾を除去する形でNormalizeしつつ、
    各Raw Char Indexが対応するNormalized Char Indexを返す(D0101.1、
    D0101-F01の修正: Post-hoc Searchを使わずFact境界をStructuralに
    Mapping変換するための基盤)。

    **Entity Decodeを行わない理由(D0101.1、D0101-F02の修正)**:
    `raw`を構成する各Tokenは、既に`xml.etree.ElementTree`がXML/XHTMLを
    Parseした結果のText(`elem.text`/`.tail`)であり、Parser自身が
    `&amp;`/`&lt;`/`&#38;`等のXML Entityを既に一度だけ解決済みである。
    この関数(旧`_normalize_joined_text`)が`html.unescape()`を追加で
    呼んでいたため、`&amp;lt;`のようなSource(DOM解決後のText`&lt;`)が
    さらに`<`へ二重Decodeされ、Source上可視のTextを無言で書き換えて
    いた(Codex Adversarial Audit Finding D0101-F02)。DOM Textは
    Entity解決済みでAuthoritativeであり、この関数はWhitespace処理
    **のみ**を行う。

    `offset_map[i]`(`i`は`0..len(raw)`)は、「Raw Position `i`の直前まで
    に確定したNormalized Text長」を表す(非空白文字については、その
    文字自身がNormalized Textへ書き込まれる正確なIndexと一致する)。
    """
    out_chars: list[str] = []
    offset_map: list[int] = [0] * (len(raw) + 1)
    pending_space = False
    started = False
    for i, ch in enumerate(raw):
        if ch.isspace():
            if started:
                pending_space = True
            offset_map[i] = len(out_chars)
        else:
            if pending_space and started:
                out_chars.append(" ")
            pending_space = False
            offset_map[i] = len(out_chars)
            out_chars.append(ch)
            started = True
    offset_map[len(raw)] = len(out_chars)
    return "".join(out_chars), offset_map


@dataclass
class _WalkResult:
    tokens: list[str]
    # (name属性値, token_start_idx, token_end_idx) のList。Document Order
    # (Text出現順)のまま保持する。
    facts: list[tuple[str, int, int]]


def _walk(elem: ET.Element, *, hidden: bool, inside_fact: bool, result: _WalkResult) -> None:
    """ElementTreeをDocument Order(`.text`→子要素→`.tail`)で再帰的に走査し、
    Hidden Subtree配下のTextを除外しつつToken Listへ集約する。同じ走査の
    中で、Hiddenでない・かつ他の`ix:nonNumeric`の内側にNestしていない
    `ix:nonNumeric`要素それぞれについて、そのSubtreeが占めるTokenの開始/
    終了Indexを記録する。この`facts`(Token Index範囲のList)から、
    `_extract_member_text_and_blocks()`がStructuralにChar Offsetを導出
    する(D0101.1、Post-hoc Searchを使わない設計、D0101-F01の修正)。

    **Nested Factの扱い(D0101、S100UP32実データ検証で発見。D0101.1
    D0101-F02 Codex Auditで`SAFE_WITH_NONBLOCKING_LIMITATION`と再分類、
    v1 Policyは維持)**: `escape="true"`の`ix:nonNumeric`(例: 半期報告書
    AuditDocの`jpcrp_cor:IndependentAuditorsReportConsolidatedTextBlock`)
    は、内側に別の`ix:nonNumeric`(監査法人名・公認会計士名等のFact)を
    Nestして持つことが実際に確認されている。D0101(初版)のPost-hoc
    Search方式では、Postorder木走査でInner FactがOuter Factより先に
    `facts`へ記録されることが`search_from`の単調増加Searchを破壊して
    いたが、D0101.1のStructural Offset方式ではその特定の破壊Mechanism
    自体は解消されている。それでもNested Factを独立Top-level Blockとして
    抽出しないPolicyは本Roundでは変更しない(D0101.1 Scope外、Hierarchy
    Model自体の設計は将来Phaseへ据え置く)——既に他の`ix:nonNumeric`の
    内側にある`ix:nonNumeric`はTop-level TextBlockとしては抽出せず、
    そのText自体はOuter FactのNormalized Textへそのまま含まれ続ける
    (情報は失われない)。"""
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


def _token_raw_span(tokens: list[str]) -> tuple[str, list[int]]:
    """`tokens`を`" ".join(tokens)`相当のRaw文字列へ結合しつつ、各Tokenが
    そのRaw文字列上で開始するIndexを返す(D0101.1、Fact境界をToken Index
    空間からRaw Char Index空間へ変換するための基盤)。"""
    raw_parts: list[str] = []
    token_raw_starts: list[int] = []
    cursor = 0
    for idx, token in enumerate(tokens):
        if idx > 0:
            raw_parts.append(" ")
            cursor += 1
        token_raw_starts.append(cursor)
        raw_parts.append(token)
        cursor += len(token)
    return "".join(raw_parts), token_raw_starts


def _extract_member_text_and_blocks(root: ET.Element) -> tuple[str, tuple[NormalizedTextBlock, ...]]:
    """D0101.1(D0101-F01の修正): Fact境界はDOM走査(`_walk`)が記録した
    Token Index範囲から、Post-hoc SearchなしにStructuralに導出する。

    手順: (1) `_walk`が集めたToken列をRaw文字列へ結合し、各Factの
    Token Index範囲をRaw Char Index範囲へ変換する。(2) Raw文字列全体を
    一度だけ`_normalize_with_offset_map()`へ通し、Member全体のNormalized
    TextとRaw→Normalized Index Mappingを得る。(3) 各FactについてRaw範囲
    内の最初/最後の非空白文字のNormalized Indexを`offset_map`から引き、
    それを`char_start`/`char_end`とする——`block.normalized_text`は
    `member_text[char_start:char_end]`の**Slice**そのものであり、
    Member Text中の別の場所を検索して一致箇所を探す操作は一切行わない
    (Ordinary Prose側の同一文言・Identical Fact同士等、内容が同じ
    別Occurrenceへ誤って結びつくことが構造的に起こり得ない)。
    """
    walk_result = _WalkResult(tokens=[], facts=[])
    _walk(root, hidden=False, inside_fact=False, result=walk_result)

    tokens = walk_result.tokens
    raw_full, token_raw_starts = _token_raw_span(tokens)
    member_text, offset_map = _normalize_with_offset_map(raw_full)

    occurrence_counters: dict[str, int] = {}
    blocks: list[NormalizedTextBlock] = []
    for name, start_idx, end_idx in walk_result.facts:
        if end_idx <= start_idx:
            continue  # Fact自身にToken(=Text)が一切無い(D0101 §7と同じ精神でSkip)

        raw_start = token_raw_starts[start_idx]
        last_token_idx = end_idx - 1
        raw_end = token_raw_starts[last_token_idx] + len(tokens[last_token_idx])

        first_non_ws: int | None = None
        last_non_ws: int | None = None
        for i in range(raw_start, raw_end):
            if not raw_full[i].isspace():
                if first_non_ws is None:
                    first_non_ws = i
                last_non_ws = i
        if first_non_ws is None or last_non_ws is None:
            continue  # Fact全体が空白のみ(実質空)

        char_start = offset_map[first_non_ws]
        char_end = offset_map[last_non_ws] + 1
        block_text = member_text[char_start:char_end]
        if len(block_text) < _MIN_TEXT_BLOCK_LENGTH:
            continue

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
