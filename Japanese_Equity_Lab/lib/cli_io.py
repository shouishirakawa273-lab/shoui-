"""CLIスクリプトの出力ストリーム符号化。

Windowsの日本語環境では、標準出力をファイルへリダイレクトするとPythonはlocale
符号化(cp932)で書き込む。日本語の多くはcp932に収まるが、em-dash(U+2014)や一部の
記号は収まらず `UnicodeEncodeError` で**1行目で落ちる**。

2026-11-22に `scripts/jquants_step3_schema_diagnostic.py` が実際にこれで死んだ。
`> step3_diag.txt` 付きで実行され、ヘッダのem-dash1文字でAPI呼び出し前に終了した。
コンソールへ直接出す分には問題なく、**リダイレクトしたときだけ落ちる**ため気付き
にくい。

## 方針

- **コンソール接続時(`isatty()`)は何もしない。** 現状の符号化で日本語は正しく
  表示されており、UTF-8へ強制するとlegacy consoleで文字化けし得る
- **リダイレクト時だけUTF-8へ固定する。** これで文字集合の制約が消える
- 人間が読むレポートは `utf-8-sig`(BOM付き)。PowerShellの `Get-Content` がBOMを
  見てUTF-8と判定するので、読む側に `-Encoding UTF8` が要らなくなる
- **機械が読むJSONは `utf-8`(BOMなし)。** BOMが付くと `json.load` が壊れる

符号化を変えるだけで、`errors` による置換に頼って情報を落とすことはしない
(`backslashreplace` は万一の保険であり、通常は発動しない)。
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from typing import Any

JSON_SAFE = "utf-8"
"""機械可読出力向け。BOMを付けない。"""

HUMAN_READABLE = "utf-8-sig"
"""人間が読むレポート向け。BOM付きでPowerShellから読みやすい。"""


def force_output_encoding(
    encoding: str = JSON_SAFE,
    *,
    streams: Sequence[Any] | None = None,
) -> tuple[str, ...]:
    """リダイレクトされたテキストストリームの符号化を固定する。

    各ストリームについて、`isatty()` が真なら触らずに現在の符号化名を返し、偽なら
    `encoding` へ切り替える。`reconfigure` を持たないストリーム(テスト用の偽物や
    差し替えられたもの)も触らない。

    戻り値は、渡された順に対応する「処理後の符号化名」。
    """
    targets = tuple(streams) if streams is not None else (sys.stdout, sys.stderr)
    results: list[str] = []
    for stream in targets:
        current = str(getattr(stream, "encoding", "") or "unknown")
        reconfigure = getattr(stream, "reconfigure", None)
        isatty = getattr(stream, "isatty", None)
        if reconfigure is None or (callable(isatty) and isatty()):
            results.append(current)
            continue
        reconfigure(encoding=encoding, errors="backslashreplace")
        results.append(encoding)
    return tuple(results)
