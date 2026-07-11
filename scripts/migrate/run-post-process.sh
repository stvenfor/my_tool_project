#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/../.."
LOG="_migrate/post-process.log"
echo "=== 后处理续跑 $(date -Iseconds) ===" | tee "$LOG"

echo "=== 重试掘金失败文档 ===" | tee -a "$LOG"
node scripts/migrate/import-to-lark.mjs --book=掘金 2>&1 | tee -a "$LOG"

for book in project code; do
  echo "=== 回写 $book ===" | tee -a "$LOG"
  node scripts/migrate/refresh-content.mjs --book="$book" 2>&1 | tee -a "$LOG"
done

echo "=== 重试默认知识库失败项 ===" | tee -a "$LOG"
node scripts/migrate/refresh-content.mjs --book=默认知识库 2>&1 | tee -a "$LOG"

echo "=== 生成报告 ===" | tee -a "$LOG"
node scripts/migrate/generate-report.mjs 2>&1 | tee -a "$LOG"
echo "=== 后处理完成 $(date -Iseconds) ===" | tee -a "$LOG"
