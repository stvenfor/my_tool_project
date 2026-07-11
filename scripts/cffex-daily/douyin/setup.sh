#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

REGISTRY="${NPM_REGISTRY:-https://registry.npmmirror.com}"

echo "→ 安装 Playwright 依赖 (registry: $REGISTRY)"
npm install --registry="$REGISTRY" --no-audit --no-fund

echo "→ 安装 Chrome 浏览器驱动"
npx playwright install chrome

echo "✅ 安装完成。下一步: node auth.mjs"
