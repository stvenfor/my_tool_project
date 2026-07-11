#!/usr/bin/env node
/**
 * 批量写回（已默认禁用，需 YUQUE_CLOUD_WRITE=1）
 */
import { spawnSync } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';
import { loadEnvLocal } from './lib/env.mjs';
import { assertCloudWriteAllowed } from './lib/cloud-write.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');

try {
  assertCloudWriteAllowed(loadEnvLocal());
} catch (err) {
  console.error(`❌ ${err.message}`);
  process.exit(1);
}

const BOOKS = process.argv.slice(2).length
  ? process.argv.slice(2)
  : [
      'English',
      'code',
      'daily',
      'project',
      'tool',
    ];

const summary = [];

for (const book of BOOKS) {
  console.log(`\n${'='.repeat(60)}\n📚 开始推送: ${book}\n${'='.repeat(60)}\n`);
  const res = spawnSync(
    'node',
    [path.join(__dirname, 'push-all.mjs'), `--book=${book}`, '--force'],
    { cwd: ROOT, stdio: 'inherit', encoding: 'utf8' },
  );
  summary.push({ book, ok: res.status === 0, status: res.status ?? 1 });
}

console.log(`\n${'='.repeat(60)}\n📊 批量推送汇总\n${'='.repeat(60)}`);
for (const row of summary) {
  console.log(`${row.ok ? '✅' : '❌'} ${row.book}`);
}
const failed = summary.filter(r => !r.ok);
if (failed.length) {
  console.log(`\n失败 ${failed.length} 个知识库，请检查 _meta/push-log.json`);
  process.exit(1);
}
console.log('\n✅ 全部知识库推送完成');
