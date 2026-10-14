"""`lib.disclosures.normalization`(Stage 3.18.2、D0101)のRegression Test。

D0100/D0100.2でEDINET実Package(臨時報告書S100TD9S・半期報告書S100UP32)に
対して手作業で確認したNormalization Rule/Exact Quote Invariant/
occurrence_index Disambiguation等を、最小のSynthetic Fixtureで固定する。
外部Fetch・実Raw Fileへの依存は一切無い(実Fileを使うAcceptance Probeは
別Script、`scripts/`配下、本Fileには含めない)。
"""

from __future__ import annotations

import io
import zipfile

import pytest
from lib.disclosures.normalization import (
    DisclosureNormalizationError,
    MemberContentType,
    NormalizedDisclosureMember,
    NormalizedTextBlock,
    normalize_edinet_type1_zip,
)
from lib.disclosures.providers.edinet_zip import compute_canonical_zip_content_hash

_XHTML_OPEN = '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:ix="http://www.xbrl.org/2008/inlineXBRL">'


def _htm(body_inner: str) -> bytes:
    return (f'<?xml version="1.0" encoding="UTF-8"?>{_XHTML_OPEN}<head></head><body>{body_inner}</body></html>').encode()


def _ix(name: str, inner: str) -> str:
    return f'<ix:nonNumeric name="{name}">{inner}</ix:nonNumeric>'


def _build_zip(entries: dict[str, bytes], *, date_time: tuple[int, int, int, int, int, int] = (2026, 1, 1, 0, 0, 0)) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in entries.items():
            info = zipfile.ZipInfo(filename=name, date_time=date_time)
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, content)
    return buf.getvalue()


_BODY_PATH = "XBRL/PublicDoc/0101010_honbun_test_ixbrl.htm"
_HEADER_PATH = "XBRL/PublicDoc/0000000_header_test_ixbrl.htm"
_AUDIT_PATH = "XBRL/AuditDoc/0000000_audit_test_ixbrl.htm"


# --- A: 基本的なInline XBRL Narrative抽出 -----------------------------------


def test_basic_valid_inline_xbrl_narrative_extraction() -> None:
    body = _ix("jpcrp_cor:BusinessRisksTextBlock", "重要な変更はありません。")
    raw_zip = _build_zip({_BODY_PATH: _htm(body)})

    doc = normalize_edinet_type1_zip(document_id="DOC1", raw_zip_bytes=raw_zip)

    assert len(doc.members) == 1
    member = doc.members[0]
    assert member.member_path == _BODY_PATH
    assert member.content_type == MemberContentType.BODY
    assert len(member.text_blocks) == 1
    block = member.text_blocks[0]
    assert block.taxonomy_element_name == "jpcrp_cor:BusinessRisksTextBlock"
    assert block.normalized_text == "重要な変更はありません。"
    assert block.occurrence_index == 0


# --- B: Mixed Content(Tag混在)の正規化 ---------------------------------------


def test_mixed_content_normalization() -> None:
    body = _ix("jpcrp_cor:DescriptionOfBusinessTextBlock", "当社は<p>自動車</p>の製造を行っています。")
    raw_zip = _build_zip({_BODY_PATH: _htm(body)})

    doc = normalize_edinet_type1_zip(document_id="DOC1", raw_zip_bytes=raw_zip)

    block = doc.members[0].text_blocks[0]
    assert block.normalized_text == "当社は 自動車 の製造を行っています。"


# --- C: HTML Entity Decoding --------------------------------------------------


def test_html_entity_decoding() -> None:
    body = _ix("jpcrp_cor:CriticalContractsForOperationTextBlock", "A&amp;B 商事との契約")
    raw_zip = _build_zip({_BODY_PATH: _htm(body)})

    doc = normalize_edinet_type1_zip(document_id="DOC1", raw_zip_bytes=raw_zip)

    block = doc.members[0].text_blocks[0]
    assert "A&B" in block.normalized_text
    assert "&amp;" not in block.normalized_text


# --- D: 空白の折り畳み ---------------------------------------------------------


def test_whitespace_collapse() -> None:
    body = _ix("jpcrp_cor:BusinessRisksTextBlock", "行１\n\n   行２\t\t行３")
    raw_zip = _build_zip({_BODY_PATH: _htm(body)})

    doc = normalize_edinet_type1_zip(document_id="DOC1", raw_zip_bytes=raw_zip)

    block = doc.members[0].text_blocks[0]
    assert block.normalized_text == "行１ 行２ 行３"


# --- E: 全角文字の保持(NFKCを適用しない) --------------------------------------


def test_fullwidth_characters_preserved() -> None:
    body = _ix("jpcrp_cor:BusinessRisksTextBlock", "１【事業等のリスク】重要な変更はありません。")
    raw_zip = _build_zip({_BODY_PATH: _htm(body)})

    doc = normalize_edinet_type1_zip(document_id="DOC1", raw_zip_bytes=raw_zip)

    block = doc.members[0].text_blocks[0]
    assert "１【事業等のリスク】" in block.normalized_text  # 全角のまま(半角への変換なし)


# --- F: style="display:none" の除外 ------------------------------------------


def test_style_display_none_excluded() -> None:
    visible = _ix("jpcrp_cor:BusinessRisksTextBlock", "可視Fact")
    hidden = f'<div style="display:none">{_ix("jpcrp_cor:HiddenFactTextBlock", "非表示Fact")}</div>'
    raw_zip = _build_zip({_BODY_PATH: _htm(visible + hidden)})

    doc = normalize_edinet_type1_zip(document_id="DOC1", raw_zip_bytes=raw_zip)

    member = doc.members[0]
    assert "非表示Fact" not in member.normalized_text
    assert "可視Fact" in member.normalized_text
    assert len(member.text_blocks) == 1
    assert member.text_blocks[0].taxonomy_element_name == "jpcrp_cor:BusinessRisksTextBlock"


# --- G: ix:hidden の除外 -------------------------------------------------------


def test_ix_hidden_excluded() -> None:
    visible = _ix("jpcrp_cor:BusinessRisksTextBlock", "可視Fact")
    hidden = f"<ix:hidden>{_ix('jpcrp_cor:HiddenFactTextBlock', '非表示Fact')}</ix:hidden>"
    raw_zip = _build_zip({_BODY_PATH: _htm(visible + hidden)})

    doc = normalize_edinet_type1_zip(document_id="DOC1", raw_zip_bytes=raw_zip)

    member = doc.members[0]
    assert "非表示Fact" not in member.normalized_text
    assert len(member.text_blocks) == 1
    assert member.text_blocks[0].taxonomy_element_name == "jpcrp_cor:BusinessRisksTextBlock"


# --- H: Document Orderの保持 ---------------------------------------------------


def test_document_order_preserved() -> None:
    body = _ix("jpcrp_cor:FirstTextBlock", "最初の内容") + _ix("jpcrp_cor:SecondTextBlock", "次の内容")
    raw_zip = _build_zip({_BODY_PATH: _htm(body)})

    doc = normalize_edinet_type1_zip(document_id="DOC1", raw_zip_bytes=raw_zip)

    blocks = doc.members[0].text_blocks
    assert [b.taxonomy_element_name for b in blocks] == ["jpcrp_cor:FirstTextBlock", "jpcrp_cor:SecondTextBlock"]
    assert blocks[0].char_start < blocks[1].char_start


# --- 追加: Nested ix:nonNumeric(実Toyota半期報告書S100UP32で実際に発見) --------


def test_nested_ix_nonnumeric_is_not_extracted_as_separate_top_level_block() -> None:
    """D0101実データ検証(S100UP32、AuditDoc)で実際に発見: `escape="true"`の
    `jpcrp_cor:IndependentAuditorsReportConsolidatedTextBlock`が、内側に
    別の`ix:nonNumeric`(監査法人名Fact等)をNestして持っていた。Nested
    Factを独立Top-level TextBlockとして扱うと、Postorder走査によりInner
    FactがOuter Factより先に記録され、search_fromの単調増加SearchでOuter
    Fact自身のOffset特定に失敗する(修正前に実際に`Disclosure
    NormalizationError`で再現した)。Nested Factは独立Blockとして抽出せず、
    そのTextはOuter FactのNormalized Textにそのまま含まれ続けることを
    固定する。"""
    inner = _ix("jpcrp_cor:AuditFirm1Consolidated", "〇〇監査法人")
    outer_name = "jpcrp_cor:IndependentAuditorsReportConsolidatedTextBlock"
    outer = (
        f'<ix:nonNumeric name="{outer_name}" escape="true">独立監査人の監査報告書 {inner} により監査を受けた。</ix:nonNumeric>'
    )
    raw_zip = _build_zip({_BODY_PATH: _htm(outer)})

    doc = normalize_edinet_type1_zip(document_id="DOC1", raw_zip_bytes=raw_zip)

    blocks = doc.members[0].text_blocks
    names = [b.taxonomy_element_name for b in blocks]
    assert names == ["jpcrp_cor:IndependentAuditorsReportConsolidatedTextBlock"]  # Inner Factは独立抽出されない
    assert "〇〇監査法人" in blocks[0].normalized_text  # Inner FactのTextはOuter Factに含まれ続ける


# --- I: 同一Taxonomy要素名の重複 → occurrence_index 0,1,... -------------------


def test_duplicate_taxonomy_element_name_gets_sequential_occurrence_index() -> None:
    body = _ix("jpcrp_cor:NameMajorShareholders", "株主A") + _ix("jpcrp_cor:NameMajorShareholders", "株主B")
    raw_zip = _build_zip({_BODY_PATH: _htm(body)})

    doc = normalize_edinet_type1_zip(document_id="DOC1", raw_zip_bytes=raw_zip)

    blocks = doc.members[0].text_blocks
    assert len(blocks) == 2
    assert blocks[0].occurrence_index == 0
    assert blocks[1].occurrence_index == 1
    assert blocks[0].normalized_text == "株主A"
    assert blocks[1].normalized_text == "株主B"


# --- J: 同一正規化Textの重複でも、順序通り別のOffsetを得る --------------------


def test_duplicate_normalized_text_gets_distinct_offsets_in_order() -> None:
    body = _ix("jpcrp_cor:NoteA", "該当事項はありません。") + _ix("jpcrp_cor:NoteB", "該当事項はありません。")
    raw_zip = _build_zip({_BODY_PATH: _htm(body)})

    doc = normalize_edinet_type1_zip(document_id="DOC1", raw_zip_bytes=raw_zip)

    blocks = doc.members[0].text_blocks
    assert blocks[0].normalized_text == blocks[1].normalized_text
    assert blocks[0].char_start < blocks[1].char_start
    member_text = doc.members[0].normalized_text
    assert member_text[blocks[0].char_start : blocks[0].char_end] == blocks[0].normalized_text
    assert member_text[blocks[1].char_start : blocks[1].char_end] == blocks[1].normalized_text


# --- K: Exact Quote Invariant(Schema制約として) --------------------------------


def test_exact_quote_invariant_enforced_on_direct_construction() -> None:
    """`normalize_edinet_type1_zip()`経由でなくとも、`NormalizedDisclosureMember`
    を直接構築すればInvariantが強制されることを確認する(Constructor-level
    Validation、D0101 §9)。"""
    bad_block = NormalizedTextBlock(
        taxonomy_element_name="jpcrp_cor:X",
        occurrence_index=0,
        normalized_text="改ざん",
        char_start=0,
        char_end=len("改ざん"),
    )
    with pytest.raises(ValueError, match="Exact Quote Invariant"):
        NormalizedDisclosureMember(
            member_path="dummy.htm",
            content_type=MemberContentType.BODY,
            normalized_text="実際のText",  # 先頭3文字は"実際の" != bad_blockの"改ざん"(範囲内・内容不一致)
            text_blocks=(bad_block,),
        )


# --- L: Invalid ZIP は失敗する --------------------------------------------------


def test_invalid_zip_fails() -> None:
    with pytest.raises(DisclosureNormalizationError):
        normalize_edinet_type1_zip(document_id="DOC1", raw_zip_bytes=b"not a zip file at all")


# --- M: Malformed XHTML は失敗する ----------------------------------------------


def test_malformed_xhtml_fails() -> None:
    malformed = b"<html><body><p>closed incorrectly</body></html>"  # </p>が無い
    raw_zip = _build_zip({_BODY_PATH: malformed})

    with pytest.raises(DisclosureNormalizationError):
        normalize_edinet_type1_zip(document_id="DOC1", raw_zip_bytes=raw_zip)


# --- N: Canonical Raw Hashが既存関数の出力と一致する ---------------------------


def test_canonical_raw_hash_matches_existing_function() -> None:
    raw_zip = _build_zip({_BODY_PATH: _htm(_ix("jpcrp_cor:X", "内容"))})

    doc = normalize_edinet_type1_zip(document_id="DOC1", raw_zip_bytes=raw_zip)

    assert doc.raw_canonical_content_hash == compute_canonical_zip_content_hash(raw_zip)


# --- O: ZIP Metadataが異なってもMember内容が同一ならRaw Hashは不変 -------------


def test_raw_hash_unchanged_when_only_zip_timestamp_differs() -> None:
    entries = {_BODY_PATH: _htm(_ix("jpcrp_cor:X", "内容"))}
    zip_old = _build_zip(entries, date_time=(2026, 8, 17, 21, 56, 12))
    zip_new = _build_zip(entries, date_time=(2026, 8, 17, 22, 33, 8))
    assert zip_old != zip_new  # Outer bytes自体は異なる(D0046と同じ実測パターン)

    doc_old = normalize_edinet_type1_zip(document_id="DOC1", raw_zip_bytes=zip_old)
    doc_new = normalize_edinet_type1_zip(document_id="DOC1", raw_zip_bytes=zip_new)

    assert doc_old.raw_canonical_content_hash == doc_new.raw_canonical_content_hash


# --- P: 非Narrative MemberはProse Blockとして出力されない ----------------------


def test_non_narrative_members_are_not_emitted_as_prose() -> None:
    raw_zip = _build_zip(
        {
            _BODY_PATH: _htm(_ix("jpcrp_cor:X", "本文Fact")),
            "XBRL/PublicDoc/test.xsd": b"<?xml version='1.0'?><schema xmlns='http://www.w3.org/2001/XMLSchema'/>",
            "XBRL/PublicDoc/test_pre.xml": b"<?xml version='1.0'?><linkbase xmlns='http://www.xbrl.org/2003/linkbase'/>",
            "XBRL/PublicDoc/test.xbrl": b"<?xml version='1.0'?><xbrl xmlns='http://www.xbrl.org/2003/instance'/>",
            "XBRL/PublicDoc/manifest_PublicDoc.xml": (
                b"<?xml version='1.0'?><manifest xmlns='http://disclosure.edinet-fsa.go.jp/2013/manifest'/>"
            ),
        }
    )

    doc = normalize_edinet_type1_zip(document_id="DOC1", raw_zip_bytes=raw_zip)

    assert len(doc.members) == 1
    assert doc.members[0].member_path == _BODY_PATH


# --- 追加: Header/Audit分類の直接確認(Content Type Classificationの健全性) ----


def test_header_and_audit_members_classified_and_normalized() -> None:
    raw_zip = _build_zip(
        {
            _HEADER_PATH: _htm(_ix("jpdei_cor:FilerNameInJapaneseDEI", "テスト株式会社")),
            _BODY_PATH: _htm(_ix("jpcrp_cor:X", "本文Fact")),
            _AUDIT_PATH: _htm(_ix("jpaud_cor:AuditReportFact", "監査報告書Fact")),
        }
    )

    doc = normalize_edinet_type1_zip(document_id="DOC1", raw_zip_bytes=raw_zip)

    content_types = {m.member_path: m.content_type for m in doc.members}
    assert content_types[_HEADER_PATH] == MemberContentType.HEADER
    assert content_types[_BODY_PATH] == MemberContentType.BODY
    assert content_types[_AUDIT_PATH] == MemberContentType.AUDIT


def test_empty_document_id_rejected() -> None:
    raw_zip = _build_zip({_BODY_PATH: _htm(_ix("jpcrp_cor:X", "内容"))})
    with pytest.raises(DisclosureNormalizationError):
        normalize_edinet_type1_zip(document_id="", raw_zip_bytes=raw_zip)


# =============================================================================
# D0101.1 — D0101-F01: Offsetは内容一致(Search)ではなくStructural Position
# から導出されることを確認する(Codex Adversarial Audit Finding)。
# =============================================================================


def _all_occurrences(haystack: str, needle: str) -> list[int]:
    positions: list[int] = []
    start = 0
    while True:
        pos = haystack.find(needle, start)
        if pos == -1:
            break
        positions.append(pos)
        start = pos + 1
    return positions


def test_f01_a_identical_prose_before_fact_binds_to_fact_occurrence() -> None:
    """通常の地の文(Prose)にFactと同じ文言が先行する場合、FactのOffsetは
    自分自身(2番目のOccurrence)を指し、Prose側(1番目)を指してはならない。"""
    body = "<p>同文</p>" + _ix("jpcrp_cor:X", "同文")
    raw_zip = _build_zip({_BODY_PATH: _htm(body)})

    doc = normalize_edinet_type1_zip(document_id="DOC1", raw_zip_bytes=raw_zip)

    member = doc.members[0]
    occurrences = _all_occurrences(member.normalized_text, "同文")
    assert len(occurrences) == 2
    block = member.text_blocks[0]
    assert block.char_start == occurrences[1]  # 2番目(Fact自身)
    assert block.char_start != occurrences[0]  # 1番目(Prose)ではない


def test_f01_b_identical_prose_after_fact_binds_to_fact_occurrence() -> None:
    """FactのTextと同じ文言が後続のProseに現れても、FactのOffsetは自分自身
    (1番目のOccurrence)を指し、後続Prose(2番目)を指してはならない。"""
    body = _ix("jpcrp_cor:X", "同文") + "<p>同文</p>"
    raw_zip = _build_zip({_BODY_PATH: _htm(body)})

    doc = normalize_edinet_type1_zip(document_id="DOC1", raw_zip_bytes=raw_zip)

    member = doc.members[0]
    occurrences = _all_occurrences(member.normalized_text, "同文")
    assert len(occurrences) == 2
    block = member.text_blocks[0]
    assert block.char_start == occurrences[0]  # 1番目(Fact自身)
    assert block.char_start != occurrences[1]  # 2番目(後続Prose)ではない


def test_f01_c_identical_prose_before_and_after_fact_binds_to_middle_occurrence() -> None:
    """前後両方に同じ文言のProseが存在する場合、FactのOffsetは3つ中2番目
    (Fact自身)を指す。"""
    body = "<p>同文</p>" + _ix("jpcrp_cor:X", "同文") + "<p>同文</p>"
    raw_zip = _build_zip({_BODY_PATH: _htm(body)})

    doc = normalize_edinet_type1_zip(document_id="DOC1", raw_zip_bytes=raw_zip)

    member = doc.members[0]
    occurrences = _all_occurrences(member.normalized_text, "同文")
    assert len(occurrences) == 3
    block = member.text_blocks[0]
    assert block.char_start == occurrences[1]  # 中央(Fact自身)


def test_f01_d_two_adjacent_identical_facts_get_distinct_structural_offsets() -> None:
    """隣接する2つの同一内容Factが、別々のStructural Offsetを得ること
    (内容一致だけでなく、独立したDOM上のOccurrenceとして扱われる)。"""
    body = _ix("jpcrp_cor:NoteA", "同文") + _ix("jpcrp_cor:NoteB", "同文")
    raw_zip = _build_zip({_BODY_PATH: _htm(body)})

    doc = normalize_edinet_type1_zip(document_id="DOC1", raw_zip_bytes=raw_zip)

    blocks = doc.members[0].text_blocks
    assert len(blocks) == 2
    assert blocks[0].char_start != blocks[1].char_start
    assert blocks[0].char_end <= blocks[1].char_start  # 範囲が重ならない


def test_f01_e_fact_text_that_is_substring_of_earlier_prose_still_correctly_located() -> None:
    """Prose自体がFactのTextを部分文字列として含む場合でも(例: Prose=
    "AAA 同文 BBB"、Fact="同文")、FactのOffsetは自分自身の独立した
    Occurrenceを指し、Prose内部への誤った位置(部分文字列一致)を指しては
    ならない。"""
    body = "<p>AAA 同文 BBB</p>" + _ix("jpcrp_cor:X", "同文")
    raw_zip = _build_zip({_BODY_PATH: _htm(body)})

    doc = normalize_edinet_type1_zip(document_id="DOC1", raw_zip_bytes=raw_zip)

    member = doc.members[0]
    occurrences = _all_occurrences(member.normalized_text, "同文")
    assert len(occurrences) == 2  # Prose内の1回 + Fact自身の1回
    block = member.text_blocks[0]
    assert block.char_start == occurrences[1]  # Fact自身(2番目)
    assert block.char_start != occurrences[0]  # Prose内部(1番目、部分文字列一致)ではない


def test_f01_f_formatting_tags_inside_fact_do_not_break_structural_offset() -> None:
    """Fact内部にFormatting Tagが混在していても、周囲のProseを含まない
    正確なStructural Offsetが得られること。"""
    body = "<p>前文</p>" + _ix("jpcrp_cor:X", "内容<b>強調</b>末尾") + "<p>後文</p>"
    raw_zip = _build_zip({_BODY_PATH: _htm(body)})

    doc = normalize_edinet_type1_zip(document_id="DOC1", raw_zip_bytes=raw_zip)

    member = doc.members[0]
    block = member.text_blocks[0]
    assert block.normalized_text == "内容 強調 末尾"
    assert member.normalized_text[block.char_start : block.char_end] == "内容 強調 末尾"
    assert "前文" not in block.normalized_text
    assert "後文" not in block.normalized_text


def test_f01_g_whitespace_collapse_across_fact_boundaries_does_not_leak_into_fact() -> None:
    """Fact直前/直後の(Fact外の)空白・改行が、Fact自身のnormalized_textへ
    先頭/末尾の空白として漏れ出さないこと。"""
    body = "<p>前文\n\n  </p>" + _ix("jpcrp_cor:X", "本体") + "<p>\n\n  後文</p>"
    raw_zip = _build_zip({_BODY_PATH: _htm(body)})

    doc = normalize_edinet_type1_zip(document_id="DOC1", raw_zip_bytes=raw_zip)

    block = doc.members[0].text_blocks[0]
    assert block.normalized_text == "本体"  # 前後の空白が漏れ出していない


def test_f01_h_hidden_nodes_adjacent_to_fact_boundaries_do_not_affect_offset() -> None:
    """Fact直前/直後にHidden Node(style=display:none)が存在しても、
    FactのOffset/Contentが汚染されないこと。"""
    hidden_before = '<div style="display:none">隠A</div>'
    hidden_after = '<div style="display:none">隠B</div>'
    body = hidden_before + _ix("jpcrp_cor:X", "本体") + hidden_after
    raw_zip = _build_zip({_BODY_PATH: _htm(body)})

    doc = normalize_edinet_type1_zip(document_id="DOC1", raw_zip_bytes=raw_zip)

    member = doc.members[0]
    block = member.text_blocks[0]
    assert block.normalized_text == "本体"
    assert "隠A" not in member.normalized_text
    assert "隠B" not in member.normalized_text
    assert member.normalized_text[block.char_start : block.char_end] == "本体"


# =============================================================================
# D0101.1 — D0101-F02: ElementTreeが既に解決したXML Entityを、二重に
# Decodeしない(Codex Adversarial Audit Finding)。
# =============================================================================


def test_f02_a_amp_amp_decodes_once_to_amp() -> None:
    """Raw Source `&amp;amp;` はXML Parserにより`&amp;`(5文字)へ一度だけ
    解決される。二重Decodeされて`&`(1文字)になってはならない。"""
    body = _ix("jpcrp_cor:X", "&amp;amp;")
    raw_zip = _build_zip({_BODY_PATH: _htm(body)})

    doc = normalize_edinet_type1_zip(document_id="DOC1", raw_zip_bytes=raw_zip)

    block = doc.members[0].text_blocks[0]
    assert block.normalized_text == "&amp;"


def test_f02_b_amp_lt_decodes_once_to_lt() -> None:
    """Raw Source `&amp;lt;` はXML Parserにより`&lt;`(4文字)へ一度だけ
    解決される。二重Decodeされて`<`になってはならない。"""
    body = _ix("jpcrp_cor:X", "&amp;lt;")
    raw_zip = _build_zip({_BODY_PATH: _htm(body)})

    doc = normalize_edinet_type1_zip(document_id="DOC1", raw_zip_bytes=raw_zip)

    block = doc.members[0].text_blocks[0]
    assert block.normalized_text == "&lt;"


def test_f02_c_numeric_entity_amp_amp_decodes_once_to_amp() -> None:
    """Raw Source `&#38;amp;`(Numeric Character Reference)も同様に、
    XML Parserにより`&amp;`(5文字)へ一度だけ解決される。"""
    body = _ix("jpcrp_cor:X", "&#38;amp;")
    raw_zip = _build_zip({_BODY_PATH: _htm(body)})

    doc = normalize_edinet_type1_zip(document_id="DOC1", raw_zip_bytes=raw_zip)

    block = doc.members[0].text_blocks[0]
    assert block.normalized_text == "&amp;"


def test_f02_d_ordinary_amp_decodes_to_single_ampersand() -> None:
    """通常のCase(Residualな二重Escapeが無い場合): Raw Source `&amp;`は
    そのまま`&`(1文字)へ解決される(既存の正しい単純Decode経路の確認)。"""
    body = _ix("jpcrp_cor:X", "A&amp;B")
    raw_zip = _build_zip({_BODY_PATH: _htm(body)})

    doc = normalize_edinet_type1_zip(document_id="DOC1", raw_zip_bytes=raw_zip)

    block = doc.members[0].text_blocks[0]
    assert block.normalized_text == "A&B"


def test_f02_e_numeric_entity_decoded_exactly_once() -> None:
    """Numeric Character Reference単体(`&#38;`)がExactly Onceだけ解決
    され、`&`(1文字)になること(Byte Literalとの比較ではなく、
    ElementTreeが構築するDOM Semanticsに対する比較で確認する)。"""
    body = _ix("jpcrp_cor:X", "&#38;")
    raw_zip = _build_zip({_BODY_PATH: _htm(body)})

    doc = normalize_edinet_type1_zip(document_id="DOC1", raw_zip_bytes=raw_zip)

    block = doc.members[0].text_blocks[0]
    assert block.normalized_text == "&"
