"""CLI出力符号化のテスト。実ストリームを壊さず偽物で検証する。

回帰の中心は2026-11-22の事故: `> file` 付きで実行された診断スクリプトが、ヘッダの
em-dash(U+2014)1文字でcp932符号化に失敗し、API呼び出し前に落ちた。
"""

from __future__ import annotations

from typing import Any

import pytest
from lib.cli_io import HUMAN_READABLE, JSON_SAFE, force_output_encoding


class FakeStream:
    """`reconfigure` と `isatty` を持つ最小のテキストストリーム代用。"""

    def __init__(self, *, encoding: str = "cp932", tty: bool = False) -> None:
        self.encoding = encoding
        self._tty = tty
        self.calls: list[dict[str, Any]] = []

    def isatty(self) -> bool:
        return self._tty

    def reconfigure(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)
        if "encoding" in kwargs:
            self.encoding = str(kwargs["encoding"])


class StreamWithoutReconfigure:
    def __init__(self, *, encoding: str = "cp932") -> None:
        self.encoding = encoding

    def isatty(self) -> bool:
        return False


def test_redirected_stream_is_switched_to_utf8() -> None:
    """[回帰] リダイレクト時はUTF-8へ固定する。cp932のままにしない。"""
    stream = FakeStream(encoding="cp932", tty=False)
    result = force_output_encoding(streams=[stream])
    assert result == (JSON_SAFE,)
    assert stream.encoding == "utf-8"
    assert stream.calls == [{"encoding": "utf-8", "errors": "backslashreplace"}]


def test_console_stream_is_left_alone() -> None:
    """コンソール接続時は触らない。日本語は現状の符号化で正しく出ている。"""
    stream = FakeStream(encoding="cp932", tty=True)
    result = force_output_encoding(streams=[stream])
    assert result == ("cp932",)
    assert stream.calls == []
    assert stream.encoding == "cp932"


def test_em_dash_survives_after_switching() -> None:
    """[回帰] 事故の原因そのもの。切り替え後の符号化でem-dashが書けること。"""
    stream = FakeStream(encoding="cp932", tty=False)
    with pytest.raises(UnicodeEncodeError):
        "J-Quants Diagnostic — observation only".encode(stream.encoding)
    force_output_encoding(streams=[stream])
    assert "J-Quants Diagnostic — observation only".encode(stream.encoding)


def test_human_readable_uses_bom_and_json_does_not() -> None:
    """BOMの有無で用途を分ける。JSONにBOMが付くと json.load が壊れる。"""
    assert "テスト".encode(HUMAN_READABLE).startswith(b"\xef\xbb\xbf")
    assert not "テスト".encode(JSON_SAFE).startswith(b"\xef\xbb\xbf")


def test_human_readable_encoding_is_applied_when_requested() -> None:
    stream = FakeStream(tty=False)
    result = force_output_encoding(HUMAN_READABLE, streams=[stream])
    assert result == (HUMAN_READABLE,)
    assert stream.encoding == "utf-8-sig"


def test_stream_without_reconfigure_is_reported_not_crashed() -> None:
    """差し替えられたストリームでも落ちない。現在の符号化名を返す。"""
    stream = StreamWithoutReconfigure(encoding="cp932")
    assert force_output_encoding(streams=[stream]) == ("cp932",)


def test_unknown_encoding_is_labelled_not_guessed() -> None:
    class Bare:
        def isatty(self) -> bool:
            return False

    assert force_output_encoding(streams=[Bare()]) == ("unknown",)


def test_multiple_streams_are_returned_in_order() -> None:
    out = FakeStream(encoding="cp932", tty=False)
    err = FakeStream(encoding="cp932", tty=True)
    assert force_output_encoding(streams=[out, err]) == ("utf-8", "cp932")


def test_empty_stream_list_is_accepted() -> None:
    assert force_output_encoding(streams=[]) == ()
