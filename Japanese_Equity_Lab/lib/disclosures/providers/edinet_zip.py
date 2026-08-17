"""EDINET Document Download(ZIP)のCanonical Content Hash(Phase4B-2、D0046追記)。

**Local Real Data Validation(2026-08-17)で確認済みの事実**: 同一`docID`・
同一`download_type`(=1)を2回Downloadしたところ、outer ZIP自体のbytes/
SHA-256は毎回異なった(`raw_retrieval_hash`が変わる)。一方、ZIP内部の各
Member(filename・byte length・content SHA-256)はすべて一致し、唯一の
差はZIP Member自体のタイムスタンプ(`2026-08-17 21:56:12` vs
`2026-08-17 22:33:08`)のみだった。**原因を断定しない**(EDINETが取得時刻を
機械的にZIP timestampへ焼き込んでいる、といった未確認の説明を事実として
書かない) — 確認できたのはあくまで`OBSERVED_BEHAVIOR`(同一文書の同一
条件でのRetrievalでも、Container Bytesが変わりうるという経験的事実)のみ。

**したがって、`Raw Artifact Identity`(取得したbytesそのものの同一性)と
`Document Content Identity`(実際のDocument内容の同一性)は別概念であり、
混同してはならない**。このModuleは後者を判定するための`Canonical Content
Hash`を提供する: ZIP Container Metadata(タイムスタンプ・圧縮方式・Member
順序)を除外し、各Memberの`filename`・`byte length`・`content SHA-256`
のみからDeterministicに計算する。

**Raw Immutability原則との関係**: このModuleはRaw ZIP bytesを一切
書き換えない(Disk展開もしない、メモリ上でのみ読み取る)。Canonical
Content Hashは既存のRaw保存(byte-for-byte immutable)に対する
Derived Metadataであり、Rawの代替ではない。

**目的はContent Identity比較のみ**であり、XBRL/PDF本文の意味解析は
一切行わない(HTML/XML/XBRL内部のWhitespace・Encoding・属性順序等を
正規化して「同じ」とみなす処理はしない — Member Raw Bytesが異なれば
Canonical Content Hashも異なる。意味的同一性判定は将来Phase)。

**Safety**(§7の要件): ZIP展開先へのDisk書き出しをしない、Path Traversal
対策(絶対Path・`..`セグメントを拒否)、Symlink等の特殊Entryをfail closed、
重複Filenameをfail closed、Malformed ZIPをfail closed、暗号化ZIPを
fail closed。
"""

from __future__ import annotations

import hashlib
import io
import logging
import stat
import zipfile
from pathlib import PurePosixPath

logger = logging.getLogger(__name__)


class ZipCanonicalizationError(Exception):
    """Malformed/Unsupported ZIP(暗号化・Symlink・Path Traversal・重複Filename等)
    によりCanonical Content Hashを計算できない場合に送出する。"""


def _is_unsafe_member_name(name: str) -> bool:
    if not name:
        return True
    if name.startswith("/") or name.startswith("\\"):
        return True
    if "\x00" in name:
        return True
    parts = PurePosixPath(name.replace("\\", "/")).parts
    return ".." in parts


def _is_symlink_entry(info: zipfile.ZipInfo) -> bool:
    unix_mode = info.external_attr >> 16
    return bool(unix_mode) and stat.S_ISLNK(unix_mode)


def _is_encrypted_entry(info: zipfile.ZipInfo) -> bool:
    return bool(info.flag_bits & 0x1)


def compute_canonical_zip_content_hash(raw_zip_bytes: bytes) -> str:
    """ZIP Container Metadataに依存しないCanonical Content Hashを計算する。

    各Member(Directory Entryを除く)について``filename``・``byte length``・
    ``SHA-256(member raw bytes)``を組にし、``filename``でSortした上で
    Deterministicに直列化してSHA-256を取る。ZIP Timestamp・圧縮方式・
    Member順序には一切依存しない(順序だけが異なる2つのZIPは同じHashに
    なることをTestで確認する)。

    以下はいずれも`ZipCanonicalizationError`としてfail closedする(解析を
    諦め、原因を推測しない): Malformed ZIP、暗号化Entry、Symlink等の
    特殊Entry、Path Traversalを含むFilename、重複Filename。
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw_zip_bytes))
    except zipfile.BadZipFile as exc:
        raise ZipCanonicalizationError(f"malformed ZIP: {exc}") from exc

    try:
        infos = zf.infolist()
    except (zipfile.BadZipFile, OSError) as exc:
        raise ZipCanonicalizationError(f"malformed ZIP central directory: {exc}") from exc

    seen_names: set[str] = set()
    canonical_entries: list[tuple[str, int, str]] = []

    for info in infos:
        name = info.filename
        if name in seen_names:
            raise ZipCanonicalizationError(f"duplicate member filename: {name!r}")
        seen_names.add(name)

        if _is_unsafe_member_name(name):
            raise ZipCanonicalizationError(f"unsafe member filename (path traversal risk): {name!r}")
        if _is_encrypted_entry(info):
            raise ZipCanonicalizationError(f"encrypted ZIP member unsupported: {name!r}")
        if _is_symlink_entry(info):
            raise ZipCanonicalizationError(f"symlink ZIP member unsupported: {name!r}")

        if name.endswith("/"):
            # Directory Entry自体はContentを持たないためCanonical Hashの対象外
            # (Directory自体の有無で内容同一性は変わらないと判断する)。
            continue

        try:
            content = zf.read(info)
        except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
            raise ZipCanonicalizationError(f"failed to read member {name!r}: {exc}") from exc

        member_hash = hashlib.sha256(content).hexdigest()
        canonical_entries.append((name, len(content), member_hash))

    canonical_entries.sort(key=lambda entry: entry[0])

    serialized = "\n".join(f"{name}\x00{length}\x00{member_hash}" for name, length, member_hash in canonical_entries)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


__all__ = ["ZipCanonicalizationError", "compute_canonical_zip_content_hash"]
