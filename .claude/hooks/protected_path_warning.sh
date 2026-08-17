#!/usr/bin/env bash
# 既存Screening Tool(core/ app.py tests/)への意図しない変更に気づけるよう
# 警告する(4A.5.1-6)。Non-blocking(常にexit 0)。Hard Blockにしない理由:
# Screening Tool自体の意図的な改修が将来必要になった場合にNoiseにしない
# ため(HOOKS_PROPOSAL.md案B、PHASE4A5_1_PLAN.mdセクションIで再確認済み)。
set -uo pipefail

cd "$(git rev-parse --show-toplevel 2>/dev/null || echo .)" || exit 0

input="$(cat)"
file_path="$(echo "$input" | jq -r '.tool_input.file_path // empty' 2>/dev/null)"

# file_pathが取得できない(未知のTool Input形状等)場合は、警告できない
# だけで静かに終了する(Fail Open、Warning自体を過信させない)。
if [ -z "$file_path" ]; then
  exit 0
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
