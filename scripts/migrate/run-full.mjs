#!/usr/bin/env node
/**
 * 全量迁移：导出 → 清洗 → 串行导入 → 同步 URL → 回写正文 → 报告
 *
 * 用法:
 *   node scripts/migrate/run-full.mjs
 *   node scripts/migrate/run-full.mjs --export-only
 *   node scripts/migrate/run-full.mjs --import-only
 *   node scripts/migrate/run-full.mjs --book=金融
 */
import { spawnSync } from 'child_process';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { CLEAN_DIR, EXPORT_DIR } from './lib/paths.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '../..');

function run(script, extraArgs = []) {
  console.log(`\n▶ node scripts/migrate/${script} ${extraArgs.join(' ')}`);
  const res = spawnSync('node', [path.join(__dirname, script), ...extraArgs], {
    cwd: ROOT,
    stdio: 'inherit',
  });
  if (res.status !== 0) process.exit(res.status ?? 1);
}

const args = process.argv.slice(2);
const exportOnly = args.includes('--export-only');
const importOnly = args.includes('--import-only');
const postOnly = args.includes('--post-only');
const bookFilter = args.find(a => a.startsWith('--book='))?.split('=')[1];

function listBooks() {
  const dir = importOnly || postOnly ? CLEAN_DIR : EXPORT_DIR;
  if (!fs.existsSync(dir)) return [];
  return fs
    .readdirSync(dir, { withFileTypes: true })
    .filter(e => e.isDirectory() && fs.existsSync(path.join(dir, e.name, 'manifest.json')))
    .map(e => e.name)
    .filter(b => !bookFilter || b === bookFilter);
}

if (!importOnly && !postOnly) {
  console.log('\n🚀 全量迁移 — 步骤 1/2: 导出 + 清洗\n');
  run('export-yuque.mjs', bookFilter ? [`--book=${bookFilter}`] : []);
  run('clean-local.mjs', bookFilter ? [`--book=${bookFilter}`] : []);
}

if (exportOnly) {
  console.log('\n✅ 导出/清洗完成（--export-only）');
  process.exit(0);
}

if (!postOnly) {
  const books = listBooks();
  console.log(`\n🚀 全量迁移 — 步骤 2/2: 串行导入（${books.length} 个知识库）\n`);
  for (const book of books) {
    console.log(`\n══════════ 知识库: ${book} ══════════`);
    run('import-to-lark.mjs', [`--book=${book}`]);
  }
}

const books = listBooks();
console.log('\n🔗 后处理: 同步 wiki URL + 回写正文链接...\n');
run('sync-wiki-urls.mjs');
for (const book of books) {
  run('refresh-content.mjs', [`--book=${book}`]);
}

console.log('\n📊 生成报告...\n');
run('generate-report.mjs', []);

console.log('\n✅ 全量迁移流程完成。请查看 _migrate/migration-report.md');
