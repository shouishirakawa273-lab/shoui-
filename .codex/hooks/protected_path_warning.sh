#!/usr/bin/env bash
# 既存Screening Tool(core/ app.py tests/)への意図しない変更に気づけるよう
# 警告する(4A.5.1-6)。Non-blocking(常にexit 0)。Hard Blockにしない理由:
# Screening Tool自体の意図的な改修が将来必要になった場合にNoiseにしない
# ため(HOOKS_PROPOSAL.md案B、PHASE4A5_1_PLAN.mdセクションIで再確認済み)。
set -uo pipefail

cd "$(git rev-parse --show-toplevel 2>/dev/null || echo .)" || exit 0

# D0098で特定した実際の根本原因: このHookは`jq`でJSON Inputを解析していたが、
# `jq`はこの開発環境(Git Bash)にインストールされておらず(`command -v jq`が
# 失敗)、`2>/dev/null`がその"jq: command not found"を無言で握りつぶしていた
# ため、`file_path`が常に空文字列になり、Warningが一切出力されないまま
# 気づかれていなかった(Path正規化の問題ではなく、外部Binary依存自体が
# 欠陥だった)。`jq`という外部Binaryへ依存せず、Repository-Local `.venv`の
# Python(`post_edit_quality_gate.sh`と同じDeterministic解決Policy、
# DECISIONS.md D0098)のStdlib `json`モジュールで解析する——Pythonも
# 見つからない場合のみ`jq`があればFallbackし、どちらも無ければFail Open
# する(既存のFail Open方針を維持、このHook自体はNon-blocking Warningの
# ままExit 0を維持する)。
PY=""
for candidate in ".venv/Scripts/python.exe" ".venv/bin/python" ".venv/bin/python3"; do
  if [ -x "$candidate" ]; then
    PY="$candidate"
    break
  fi
done

# D0098で追加特定した根本原因(2件目): Tool InputのJSONは`file_path`へ
# 日本語ユーザー名(Unicode)を含む(このRepository自体が`C:\Users\<日本語
# ユーザー名>\...`配下にあるため)。この環境のPython Stdin/Stdoutの既定
# Encodingは`sys.stdin.encoding`実測で`cp932`(Windows日本語Codepage)で
# あり、UTF-8のJSONをBash経由でStdin Text Modeへそのまま渡すと、Unicode
# 文字に隣接するバイト列が破損する(実測確認済み、DECISIONS.md D0098)。
# Stdinを一度Temp Fileへ書き出し、Python側は`argv`でFile Pathを受け取り
# `rb`でOpenして明示的に`.decode("utf-8")`する(Bash変数への往復・Stdin
# Text Modeの既定Encodingのいずれにも依存しない)。
tmp_input="$(mktemp)"
trap 'rm -f "$tmp_input"' EXIT
cat > "$tmp_input"

if [ -n "$PY" ]; then
  file_path="$("$PY" -c '
import json
import sys

value = None
try:
    with open(sys.argv[1], "rb") as f:
        data = json.loads(f.read().decode("utf-8"))
except Exception:
    value = None
else:
    value = data.get("tool_input", {}).get("file_path")

if value:
    sys.stdout.buffer.write(value.encode("utf-8"))
' "$tmp_input" 2>/dev/null)"
elif command -v jq >/dev/null 2>&1; then
  file_path="$(jq -r '.tool_input.file_path // empty' < "$tmp_input" 2>/dev/null)"
else
  file_path=""
fi

# file_pathが取得できない(未知のTool Input形状・Parser利用不可等)場合は、
# 警告できないだけで静かに終了する(Fail Open、Warning自体を過信させない)。
if [ -z "$file_path" ]; then
  exit 0
fi

# D0098で特定した既知の欠陥: Windows上のClaude Codeはtool_input.file_path
# をWindowsスタイル(バックスラッシュ・ドライブレター、例: C:\Users\...\
# core\models.py)で渡すが、このHook自身はGit Bash(POSIX-style pwd、例:
# /c/Users/.../shoui-)上で動作するため、単純なPrefix比較では一致せず、
# Warningが常に出力されない(Silent False Negative)まま気づかれていなかった。
# Git Bash同梱の`cygpath`が利用可能ならPOSIX形式へ正規化してから比較する
# (利用不可な環境向けにNormalize失敗時は元のfile_pathへFail Open)。
if command -v cygpath >/dev/null 2>&1; then
  file_path="$(cygpath -u "$file_path" 2>/dev/null || echo "$file_path")"
fi

# 絶対Path・相対Pathいずれでも、Repository Root相対に正規化して判定する。
relative_path="${file_path#"$(pwd)"/}"

case "$relative_path" in
  core/*|core|app.py|tests/*|tests)
    echo "[hook][WARNING] ${relative_path} は既存Screening Tool(core/ app.py tests/)配下です。" >&2
    echo "[hook][WARNING] Japanese_Equity_Labの作業でこのPathを意図的に変更していますか?" >&2
    echo "[hook][WARNING] 意図しない変更であれば、変更内容を確認してください(このHookはBlockしません)。" >&2
    ;;
esac

exit 0
