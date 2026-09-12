#!/usr/bin/env bash
# ファイル編集後の品質ゲート。lint / 型チェック / テストを実行し、
# 失敗した場合は非ゼロで終了してClaude Codeに次の手を止めさせる。
#
# Python解決Policy(D0098、Deterministic Repository-Local Toolchain):
# このRepositoryのVenvは常に`<repo>/.venv`直下にあるという前提のみを
# 置き、そこからRepo-Root-Relativeに解決する。グローバルPython・
# `%LOCALAPPDATA%`のPython・PATH上でたまたま先頭に来た`python`/`python3`
# へは一切Fallbackしない(D0098以前は`.venv/bin/python`固定でWindows
# Venv実体の`.venv/Scripts/python.exe`を検出できず、存在しない`python3`
# へFallbackしていた結果、Windows App Execution Aliasが解決するToolingを
# 一切持たないGlobal Pythonが選ばれ、"No module named ruff/mypy/pytest"
# が発生していた——DECISIONS.md D0098参照)。
set -uo pipefail

cd "$(git rev-parse --show-toplevel 2>/dev/null || echo .)" || exit 1

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
  echo "[hook] リポジトリRootで .venv を作成し、ruff/mypy/pytest等の依存関係をインストールしてください。" >&2
  exit 2
fi

# 選択したInterpreterが実際にQuality Gate Toolを持っているかを、Gate実行前に
# 検証する(D0098要件v1 §7)。Toolが無い場合はBareなTracebackではなく、原因と
# 対処が分かるMessageでfail closedする(Silent Fallback・Silent Skip禁止)。
missing_modules=""
for module in ruff mypy pytest; do
  if ! "$PY" -c "import ${module}" >/dev/null 2>&1; then
    missing_modules="${missing_modules} ${module}"
  fi
done
if [ -n "$missing_modules" ]; then
  echo "[hook] ${PY} に以下のModuleが見つかりません:${missing_modules}" >&2
  echo "[hook] 例: ${PY} -m pip install ruff mypy pytest" >&2
  echo "[hook] (Repository-local .venvへインストールしてください、Global Pythonへは切り替えません)" >&2
  exit 2
fi

fail=0

echo "[hook] ruff check ..."
"$PY" -m ruff check . || fail=1

echo "[hook] ruff format --check ..."
"$PY" -m ruff format --check . || fail=1

echo "[hook] mypy ..."
"$PY" -m mypy core app.py scripts Japanese_Equity_Lab/lib || fail=1

echo "[hook] pytest ..."
"$PY" -m pytest tests/ Japanese_Equity_Lab/13_tests/ -q || fail=1

if [ "$fail" -ne 0 ]; then
  echo "[hook] 品質ゲートに失敗しました。上記のエラーを修正してください。" >&2
  exit 2
fi

echo "[hook] 品質ゲートOK"
exit 0
