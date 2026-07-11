#!/bin/bash
# 全量串行导入（后台运行）
set -euo pipefail
cd "$(dirname "$0")/../.."
LOG="_migrate/full-import.log"
BOOKS=(eav1v0 daily 飞书 金融 English 掘金 tool 默认知识库 project code)

echo "=== 全量导入开始 $(date -Iseconds) ===" | tee -a "$LOG"
TOTAL=0
for book in "${BOOKS[@]}"; do
  echo "" | tee -a "$LOG"
  echo "========== $book $(date -Iseconds) ==========" | tee -a "$LOG"
  node scripts/migrate/import-to-lark.mjs --book="$book" 2>&1 | tee -a "$LOG"
done

echo "" | tee -a "$LOG"
echo "=== 同步 URL $(date -Iseconds) ===" | tee -a "$LOG"
node scripts/migrate/sync-wiki-urls.mjs 2>&1 | tee -a "$LOG"

for book in "${BOOKS[@]}"; do
  echo "=== 回写 $book $(date -Iseconds) ===" | tee -a "$LOG"
  node scripts/migrate/refresh-content.mjs --book="$book" 2>&1 | tee -a "$LOG"
done

echo "=== 生成报告 $(date -Iseconds) ===" | tee -a "$LOG"
node scripts/migrate/generate-report.mjs 2>&1 | tee -a "$LOG"
echo "=== 全量迁移完成 $(date -Iseconds) ===" | tee -a "$LOG"
