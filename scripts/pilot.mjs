#!/usr/bin/env node
/**
 * 试点流程：备份 → 规则优化 → 生成 diff →（可选）写回
 *
 * 用法:
 *   node scripts/yuque/pilot.mjs --folder=某文件夹名
 *   node scripts/yuque/pilot.mjs --folder=某文件夹名 --push
 */
import { spawnSync } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';
import { getYuqueRoot, loadEnvLocal } from './lib/env.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');

function run(script, extraArgs = []) {
  const res = spawnSync('node', [path.join(__dirname, script), ...extraArgs], {
    cwd: ROOT,
    stdio: 'inherit',
  });
  if (res.status !== 0) {
    process.exit(res.status ?? 1);
  }
}

const args = process.argv.slice(2);
const folder = args.find(a => a.startsWith('--folder='))?.split('=')[1];
const shouldPush = args.includes('--push');

if (!folder) {
  console.error('用法: npm run pilot -- --folder=文件夹名 [--push]');
  process.exit(1);
}

console.log(`\n🧪 试点文件夹: ${folder}\n`);

run('backup.mjs', [`--label=pilot-${folder.replace(/[^\w\u4e00-\u9fff-]/g, '_')}`]);
run('optimize-rules.mjs', [`--folder=${folder}`]);
run('generate-diff.mjs');

if (shouldPush) {
  console.log('\n📤 开始写回...\n');
  run('push-all.mjs', [`--folder=${folder}`]);
} else {
  const dataDir = getYuqueRoot(loadEnvLocal());
  console.log(`\n✅ 试点完成。审核 ${dataDir}/_reports/diff-summary.json 后，执行:`);
  console.log(`   npm run push -- --folder=${folder}`);
}
