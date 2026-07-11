#!/usr/bin/env node
/**
 * 试点迁移：导出 → 清洗 → 导入（默认读取 _migrate/pilot-docs.json）
 *
 * 用法:
 *   node scripts/migrate/run-pilot.mjs
 *   node scripts/migrate/run-pilot.mjs --export-only
 *   node scripts/migrate/run-pilot.mjs --import-only
 *   node scripts/migrate/run-pilot.mjs --dry-run
 */
import { spawnSync } from 'child_process';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '../..');

function run(script, extraArgs = []) {
  const res = spawnSync('node', [path.join(__dirname, script), ...extraArgs], {
    cwd: ROOT,
    stdio: 'inherit',
  });
  if (res.status !== 0) process.exit(res.status ?? 1);
}

const args = process.argv.slice(2);
const exportOnly = args.includes('--export-only');
const importOnly = args.includes('--import-only');
const dryRun = args.includes('--dry-run');

const pilotListPath = path.join(ROOT, '_migrate/pilot-docs.json');
const pilotCount = fs.existsSync(pilotListPath)
  ? JSON.parse(fs.readFileSync(pilotListPath, 'utf8')).length
  : 0;

console.log(`\n🚀 语雀→飞书 试点迁移（${pilotCount} 篇，见 _migrate/pilot-docs.json）\n`);

if (!importOnly) {
  console.log('── 步骤 1/4: 导出语雀 ──');
  run('export-yuque.mjs', ['--pilot']);

  console.log('\n── 步骤 2/4: 清洗本地文件 ──');
  run('clean-local.mjs', []);
}

if (exportOnly) {
  console.log('\n✅ 导出/清洗完成（--export-only，跳过飞书导入）');
  run('generate-report.mjs', []);
  process.exit(0);
}

console.log('\n── 步骤 3/4: 导入飞书并移入知识库 ──');
const cleanDir = path.join(ROOT, '_migrate/clean');
if (fs.existsSync(cleanDir)) {
  for (const entry of fs.readdirSync(cleanDir, { withFileTypes: true })) {
    if (!entry.isDirectory()) continue;
    const manifestPath = path.join(cleanDir, entry.name, 'manifest.json');
    if (!fs.existsSync(manifestPath)) continue;
    const importArgs = [`--book=${entry.name}`];
    if (dryRun) importArgs.push('--dry-run');
    run('import-to-lark.mjs', importArgs);
  }
}

console.log('\n── 步骤 4/4: 生成报告 ──');
run('generate-report.mjs', []);

console.log('\n✅ 试点流程完成。请检查 _migrate/migration-report.md');
console.log('   确认无误后，可执行全量迁移（去掉 --pilot 限制）。');
