#!/usr/bin/env bash
# Post-Edit Fast Gate(D0098 Layer A: Fast Fail-Fast Gate)。
# 目的: 数秒で終わる低負荷checkのみを行う。full pytest/repo-wide mypy/
# repo-wide scanは一切実行しない。
#
# D0098 Root Cause 2(Resource Exhaustion): 旧版はEdit/Write/MultiEditの
# たびにrepo全体のruff/format/mypyに加えてfull pytest(tests/・
# Japanese_Equity_Lab/13_tests/の全件)まで起動していた。さらにpytest内の
# Hook Integration Testsがこのscript自身をsubprocessで再起動し、その中で
# 再度full pytestが走る構造になっており、1回のEditで数段Nestした重い
# Processが多重発生していた——PC Crash / 極端なCPU-RAM-I/O消費の最有力
# 原因(DECISIONS.md D0098参照)。
#
# 新Policy: Post-Edit(このScript)= 低負荷Fast Gateのみ。mypy・pytestは
# ここから完全に削除し、Task/Stage完了時の明示的なTargeted/Full
# Acceptance(人間/Main Claudeが手動実行)へ移す。品質基準を削除したの
# ではなく、実行Timingを分離しただけ(DECISIONS.md D0098)。
#
# Layer B(Targeted Acceptance)・Layer C(Full Acceptance)は、このHookから
# は絶対に呼び出さない。このScript自身もPytest/Mypy/自分自身の再起動を
# 一切行わない(Recursion Structureを構造的に排除する)。
#
# Python解決Policy(D0098、Deterministic Repository-Local Toolchain、
# 変更なし): このRepositoryのVenvは常に`<repo>/.venv`直下にあるという
# 前提のみを置き、そこからRepo-Root-Relativeに解決する。グローバル
# Python・`%LOCALAPPDATA%`のPython・PATH上でたまたま先頭に来た
# `python`/`python3`へは一切Fallbackしない。
#
# Repository Boundary Guard(D0098.1): D0098時点ではtool_input.file_path
# が実際にこのRepository配下かどうかを検証しておらず、Claude Scratchpad
# 等Repository外の`.py`File(例: `%LOCALAPPDATA%\...\scratchpad\*.py`)への
# EditでもこのRepositoryの`pyproject.toml`(line-length等)を使ってruffを
# 実行し、Repository外Fileの整形差分だけでFast Gateが失敗していた
# (SCRATCHPAD_FALSE_POSITIVE、DECISIONS.md D0098.1参照)。以下で取得する
# `repo_root`をPython側のMembership Check(`Path.relative_to()`、素朴な
# 文字列Prefix比較ではなくPath Parts単位の比較)に渡し、Repository外の
# Fileは判定できない場合と同じFail Open経路(skip)で扱う。
set -uo pipefail

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$repo_root" || exit 1

PY=""
for candidate in ".venv/Scripts/python.exe" ".venv/bin/python" ".venv/bin/python3"; do
  if [ -x "$candidate" ]; then
    PY="$candidate"
    break
  fi
done

if [ -z "$PY" ]; then
  echo "[hook] リポジトリ直下に.venv(.venv/Scripts/python.exeまたは.venv/bin/python)が見つかりません。" >&2
  echo "[hook] Global Pythonへは自動Fallbackしません(Deterministic Toolchain Policy、DECISIONS.md D0098)。" >&2
  echo "[hook] リポジトリRootで .venv を作成し、ruff等の依存関係をインストールしてください。" >&2
  exit 2
fi

# Fast GateはruffのみをUseする(mypy/pytestはTargeted/Full Acceptanceへ
# 移したため、ここではImport検証もruffのみに限定する、DECISIONS.md D0098)。
if ! "$PY" -c "import ruff" >/dev/null 2>&1; then
  echo "[hook] ${PY} にruffが見つかりません。" >&2
  echo "[hook] 例: ${PY} -m pip install ruff" >&2
  echo "[hook] (Repository-local .venvへインストールしてください、Global Pythonへは切り替えません)" >&2
  exit 2
fi

# Tool Inputから変更対象file_pathを取得する(Unicode-safe: Stdinを一度
# Temp Fileへ書き出し、Repository-local PythonがargvでFile Pathを受け取り
# `rb`でOpenして明示的に`.decode("utf-8")`する。Bash変数への往復・Stdin
# Text Modeの既定Encoding(cp932)には依存しない、protected_path_
# warning.shと同じ方式)。
tmp_input="$(mktemp)"
trap 'rm -f "$tmp_input"' EXIT
cat > "$tmp_input"

file_path="$("$PY" -c '
import json
import sys
from pathlib import Path

value = None
try:
    with open(sys.argv[1], "rb") as f:
        data = json.loads(f.read().decode("utf-8"))
except Exception:
    value = None
else:
    value = data.get("tool_input", {}).get("file_path")

if value:
    # Repository Boundary Guard(D0098.1): Path Parts単位のMembership Check
    # (`relative_to()`)であり、素朴な文字列Prefix比較ではない
    # (`repo_root=/x/repo`に対して`/x/repo-other/y.py`のような
    # Near-Prefix Pathを誤って内側と判定しない)。File自体が存在しなくても
    # `resolve()`できるため(Edit直後でまだ存在しない場合を含む)、
    # 存在確認は別途後段で行う。
    try:
        candidate_resolved = Path(value).resolve()
        candidate_resolved.relative_to(Path(sys.argv[2]).resolve())
    except (OSError, ValueError):
        value = None

if value:
    sys.stdout.buffer.write(value.encode("utf-8"))
' "$tmp_input" "$repo_root" 2>/dev/null)"

# file_pathが取得できない場合(Tool Input未解決、またはRepository外)は、
# Fast Gateを安全側でskipする(Fail Open。判定できないだけで、Blockは
# しない——Protected Path Warningと同じ方針)。
if [ -z "$file_path" ]; then
  echo "[hook] file_pathを取得できなかった、またはRepository外のためFast Gateをskipします。" >&2
  exit 0
fi

if command -v cygpath >/dev/null 2>&1; then
  file_path="$(cygpath -u "$file_path" 2>/dev/null || echo "$file_path")"
fi

# .py以外はPython Quality Toolを起動しない(non-Python Editで不要な
# Processを起動しない、DECISIONS.md D0098要件)。
case "$file_path" in
  *.py) ;;
  *)
    exit 0
    ;;
esac

# Edit/Write/MultiEditは既存Fileへの書き込みのみでdeleteは発生しないが、
# 念のため存在確認してから対象にする(削除されたFileへruffを実行しない)。
if [ ! -f "$file_path" ]; then
  exit 0
fi

fail=0

echo "[hook] ruff check (changed file only) ..."
"$PY" -m ruff check "$file_path" || fail=1

echo "[hook] ruff format --check (changed file only) ..."
"$PY" -m ruff format --check "$file_path" || fail=1

if [ "$fail" -ne 0 ]; then
  echo "[hook] Fast Gateに失敗しました。上記のエラーを修正してください。" >&2
  echo "[hook] (mypy/pytestはPost-Edit Gate対象外です。Task/Stage完了時にTargeted/Full Acceptanceを実行してください、DECISIONS.md D0098)" >&2
  exit 2
fi

echo "[hook] Fast Gate OK(ruff: 変更Fileのみ。mypy/pytestは対象外、DECISIONS.md D0098)"
exit 0
