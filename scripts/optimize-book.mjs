#!/usr/bin/env node
/**
 * 按知识库分步优化：备份 → 规则优化 → diff
 *
 * npm run optimize-book -- 金融
 * npm run optimize-book -- --next        # 按 book_order 优化下一个
 * npm run optimize-book -- 金融 --push     # 已禁用，不会写回语雀
 */
import fs from 'fs';
import path from 'path';
import { spawnSync } from 'child_process';
import { load as loadYaml } from 'js-yaml';
import { fileURLToPath } from 'url';
import { META_DIR, RULES_PATH } from './lib/env.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const PROGRESS_PATH = path.join(META_DIR, 'optimize-progress.json');

function run(script, extraArgs = []) {
  const res = spawnSync('node', [path.join(__dirname, script), ...extraArgs], {
    cwd: ROOT,
    stdio: 'inherit',
  });
  if (res.status !== 0) {
    process.exit(res.status ?? 1);
  }
}

function loadBookOrder() {
  if (!fs.existsSync(RULES_PATH)) return [];
  const rules = loadYaml(fs.readFileSync(RULES_PATH, 'utf8'));
  return rules.book_order || [];
}

function loadProgress() {
  if (!fs.existsSync(PROGRESS_PATH)) {
    return { completed: [], current: null };
  }
  return JSON.parse(fs.readFileSync(PROGRESS_PATH, 'utf8'));
}

function saveProgress(progress) {
  fs.mkdirSync(META_DIR, { recursive: true });
  fs.writeFileSync(PROGRESS_PATH, JSON.stringify(progress, null, 2));
}

function resolveBook(args) {
  const explicit = args.find(a => !a.startsWith('--'));
  if (explicit) return explicit;

  if (args.includes('--next')) {
    const order = loadBookOrder();
    const { completed } = loadProgress();
    const next = order.find(b => !completed.includes(b));
    if (!next) {
      console.log('✅ 所有知识库均已优化完成');
      process.exit(0);
    }
    return next;
  }

  console.error('用法: npm run optimize-book -- 金融 [--push]');
  console.error('      npm run optimize-book -- --next [--push]');
  process.exit(1);
}

const args = process.argv.slice(2);
const book = resolveBook(args);
const shouldPush = args.includes('--push');
const label = `book-${book.replace(/[^\w\u4e00-\u9fff-]/g, '_')}`;

console.log(`\n📚 优化知识库: ${book}\n`);

run('backup.mjs', [`--book=${book}`, `--label=${label}`]);
run('optimize-rules.mjs', [`--book=${book}`]);
run('generate-diff.mjs', [`--book=${book}`, `--backup=${label}`]);

const progress = loadProgress();
if (!progress.completed.includes(book)) {
  progress.completed.push(book);
}
progress.current = book;
progress.updated_at = new Date().toISOString();
saveProgress(progress);

const order = loadBookOrder();
const nextBook = order.find(b => !progress.completed.includes(b));

console.log(`\n✅ 「${book}」优化完成`);
console.log(`   变更报告: _reports/diff-summary.json`);
if (nextBook) {
  console.log(`   下一个: npm run optimize-book -- ${nextBook}`);
} else if (order.length) {
  console.log('   全部知识库已优化');
}

if (shouldPush) {
  console.error('\n❌ 已禁用优化后自动写回语雀云端。');
  console.error('   本地优化不会同步到语雀，请在语雀网页端正常编辑。');
  console.error('   如需拉取云端：npm run sync-all');
  console.error('   如确需写回（不推荐）：在 .env.local 设置 YUQUE_CLOUD_WRITE=1 后执行 npm run push\n');
  process.exit(1);
} else {
  console.log(`\n本地优化已完成，未写回语雀。`);
  console.log(`   拉取云端最新：npm run sync-all`);
  console.log(`   查看本地 diff：_reports/diff-summary.json\n`);
}
