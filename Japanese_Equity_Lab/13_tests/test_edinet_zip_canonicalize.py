"""Phase4B-2(D0046追記): `lib.disclosures.providers.edinet_zip`のテスト。

2026-08-17のLocal Real Data Validationで観測された「同一docID・同一
download_typeでもouter ZIP bytesがRetrievalごとに変わりうる(ZIP Member
Timestampが変わる)」という実挙動を、Synthetic Fixtureで再現する
Regression Testを含む。外部呼び出しは一切行わない。
"""

from __future__ import annotations

import io
import zipfile

import pytest
from lib.disclosures.providers.edinet_zip import ZipCanonicalizationError, compute_canonical_zip_content_hash


def _build_zip(
    entries: list[tuple[str, bytes]],
    *,
    date_time: tuple[int, int, int, int, int, int] = (2026, 8, 17, 21, 56, 12),
    compress_type: int = zipfile.ZIP_DEFLATED,
) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in entries:
            info = zipfile.ZipInfo(filename=name, date_time=date_time)
            info.compress_type = compress_type
            zf.writestr(info, content)
    return buf.getvalue()


_MEMBERS = [("XBRL/PublicDoc/doc.xbrl", b"xbrl-content-here"), ("meta/manifest.xml", b"manifest-content")]


# --- Local Real Data Validationの再現: Timestampのみ異なる ---


def test_same_content_different_timestamps_outer_differs_but_canonical_matches() -> None:
    """2026-08-17のLocal Real Data Validationの直接的な再現: 同じMember内容、
    ZIP Timestampだけが異なる2つのZIP(OLD 21:56:12 / NEW 22:33:08相当)。
    outer bytesは異なるが、Canonical Content Hashは一致する。"""
    zip_old = _build_zip(_MEMBERS, date_time=(2026, 8, 17, 21, 56, 12))
    zip_new = _build_zip(_MEMBERS, date_time=(2026, 8, 17, 22, 33, 8))

    assert zip_old != zip_new  # outer bytesは異なる(Local実データと同じ)
    hash_old = compute_canonical_zip_content_hash(zip_old)
    hash_new = compute_canonical_zip_content_hash(zip_new)
    assert hash_old == hash_new  # Canonical Content Hashは一致する


# --- 実際に内容が変わった場合はCanonical Hashも変わる ---


def test_member_content_changed_canonical_hash_changes() -> None:
    base = _build_zip(_MEMBERS)
    changed = _build_zip([("XBRL/PublicDoc/doc.xbrl", b"DIFFERENT-content"), _MEMBERS[1]])
    assert compute_canonical_zip_content_hash(base) != compute_canonical_zip_content_hash(changed)


def test_member_filename_changed_canonical_hash_changes() -> None:
    base = _build_zip(_MEMBERS)
    renamed = _build_zip([("XBRL/PublicDoc/renamed.xbrl", _MEMBERS[0][1]), _MEMBERS[1]])
    assert compute_canonical_zip_content_hash(base) != compute_canonical_zip_content_hash(renamed)


def test_member_added_canonical_hash_changes() -> None:
    base = _build_zip(_MEMBERS)
    with_extra = _build_zip([*_MEMBERS, ("extra/new_file.txt", b"new")])
    assert compute_canonical_zip_content_hash(base) != compute_canonical_zip_content_hash(with_extra)


def test_member_deleted_canonical_hash_changes() -> None:
    base = _build_zip(_MEMBERS)
    fewer = _build_zip(_MEMBERS[:1])
    assert compute_canonical_zip_content_hash(base) != compute_canonical_zip_content_hash(fewer)


# --- Container Metadataのみの違い(順序・圧縮方式)はCanonical Hashに影響しない ---


def test_member_ordering_only_canonical_hash_unchanged() -> None:
    forward = _build_zip(_MEMBERS)
    reversed_order = _build_zip(list(reversed(_MEMBERS)))
    assert forward != reversed_order  # outer bytesはOrder依存で異なりうる
    assert compute_canonical_zip_content_hash(forward) == compute_canonical_zip_content_hash(reversed_order)


def test_compression_level_only_change_does_not_affect_canonical_hash() -> None:
    stored = _build_zip(_MEMBERS, compress_type=zipfile.ZIP_STORED)
    deflated = _build_zip(_MEMBERS, compress_type=zipfile.ZIP_DEFLATED)
    # 圧縮方式が異なればouter bytesは通常異なる。
    assert stored != deflated
    assert compute_canonical_zip_content_hash(stored) == compute_canonical_zip_content_hash(deflated)


# --- Safety: Malformed / Path Traversal / Symlink / 重複Filename / 暗号化 ---


def test_malformed_zip_fails_closed() -> None:
    with pytest.raises(ZipCanonicalizationError):
        compute_canonical_zip_content_hash(b"this is not a zip file at all")


def test_duplicate_filename_fails_closed() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("same_name.txt", b"first")
        zf.writestr("same_name.txt", b"second")
    with pytest.raises(ZipCanonicalizationError, match="duplicate"):
        compute_canonical_zip_content_hash(buf.getvalue())


def test_path_traversal_filename_fails_closed() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../../etc/passwd", b"malicious")
    with pytest.raises(ZipCanonicalizationError, match="unsafe member filename"):
        compute_canonical_zip_content_hash(buf.getvalue())


def test_absolute_path_filename_fails_closed() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("/etc/passwd", b"malicious")
    with pytest.raises(ZipCanonicalizationError, match="unsafe member filename"):
        compute_canonical_zip_content_hash(buf.getvalue())


def test_symlink_entry_fails_closed() -> None:
    import stat

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        info = zipfile.ZipInfo(filename="link_to_something")
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        zf.writestr(info, b"/etc/passwd")
    with pytest.raises(ZipCanonicalizationError, match="symlink"):
        compute_canonical_zip_content_hash(buf.getvalue())


def _mark_general_purpose_flag_bit0(raw: bytes) -> bytes:
    """`zipfile.ZipFile.writestr`はGeneral Purpose Bit Flagを内部で再計算して
    上書きしてしまう(Unicode Filename判定以外のFlagはClearされる)ため、
    暗号化Flag(bit 0)を確認するTest用に、生成済みZIP bytesへ直接Patchする
    (Local File Header・Central Directory Header双方のFlag Byteを立てる)。"""
    data = bytearray(raw)
    for signature, flag_offset in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
        idx = data.find(signature)
        while idx != -1:
            data[idx + flag_offset] |= 0x01
            idx = data.find(signature, idx + len(signature))
    return bytes(data)


def test_encrypted_entry_fails_closed() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("secret.txt", b"encrypted-looking-content")
    raw = _mark_general_purpose_flag_bit0(buf.getvalue())
    with pytest.raises(ZipCanonicalizationError, match="encrypted"):
        compute_canonical_zip_content_hash(raw)


def test_directory_entries_do_not_affect_canonical_hash() -> None:
    """Directory Entry自体はContentを持たないため、Canonical Hashの計算対象から
    除外する(その有無だけで別文書とみなさない)。"""
    buf_without_dir = io.BytesIO()
    with zipfile.ZipFile(buf_without_dir, "w") as zf:
        zf.writestr("meta/manifest.xml", b"content")

    buf_with_dir = io.BytesIO()
    with zipfile.ZipFile(buf_with_dir, "w") as zf:
        zf.writestr("meta/", b"")
        zf.writestr("meta/manifest.xml", b"content")

    assert compute_canonical_zip_content_hash(buf_without_dir.getvalue()) == compute_canonical_zip_content_hash(
        buf_with_dir.getvalue()
    )


# --- Offline再現性 / Determinism ---


def test_canonical_hash_is_pure_and_deterministic() -> None:
    raw = _build_zip(_MEMBERS)
    assert compute_canonical_zip_content_hash(raw) == compute_canonical_zip_content_hash(raw)


def test_raw_bytes_are_not_mutated_by_canonicalization() -> None:
    """Canonical Hash計算はRaw bytesを一切書き換えない(引数のbytesが不変)。"""
    raw = _build_zip(_MEMBERS)
    raw_copy = bytes(raw)
    compute_canonical_zip_content_hash(raw)
    assert raw == raw_copy


# --- §11 PIT/Revision Implication: raw_retrieval_hashの不一致だけで
#     DocumentRelationship(訂正・改版)を推論しないことの構造的確認 ---


def test_edinet_zip_module_never_constructs_document_relationship() -> None:
    """`raw_retrieval_hash`の不一致(Container Bytesの違い)だけをもって
    「Documentが訂正・改版された」と自動推論するコードが存在しないことを
    Import構造で確認する(D0046追記 §11)。`DocumentRelationship`は
    `lib.disclosures.model`が要求する通り、明示的な根拠(`basis`)がある
    場合のみMain Claudeが手動で構築するものであり、Hash比較から自動生成
    しない。"""
    import lib.disclosures.providers.edinet_zip as edinet_zip_module

    source = edinet_zip_module.__file__
    assert source is not None
    with open(source, encoding="utf-8") as f:
        text = f.read()
    assert "DocumentRelationship" not in text
    assert "DuplicateRelationKind" not in text
