#!/usr/bin/env bash
# TEST-001: 型チェック(pnpm typecheck)。cwd = 生成プロジェクト直下。exit 0 = PASS
# 使い方: bash recipe-tests/smoke-typecheck.sh
set -u
if ! command -v pnpm >/dev/null 2>&1; then
  echo "FAIL: pnpm が無い(knowledge/pnpm.md を参照)"; exit 1
fi
if [[ ! -f package.json ]]; then
  echo "FAIL: package.json が無い(cwd は生成プロジェクト直下で実行する)"; exit 1
fi
if ! grep -q '"typecheck"' package.json; then
  echo "FAIL: package.json に typecheck スクリプトが無い(\"typecheck\": \"tsc --noEmit\" を足す)"; exit 1
fi
if pnpm typecheck; then
  echo "PASS: pnpm typecheck 型エラー 0"; exit 0
fi
echo "FAIL: pnpm typecheck に型エラーあり"; exit 1
