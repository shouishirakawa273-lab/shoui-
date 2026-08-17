#!/usr/bin/env bash
# ファイル編集後の品質ゲート。lint / 型チェック / テストを実行し、
# 失敗した場合は非ゼロで終了してClaude Codeに次の手を止めさせる。
set -uo pipefail

cd "$(git rev-parse --show-toplevel 2>/dev/null || echo .)" || exit 1

PY=".venv/bin/python"
if [ ! -x "$PY" ]; then
  # venv未作成のローカル環境向けフォールバック
  PY="python3"
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
