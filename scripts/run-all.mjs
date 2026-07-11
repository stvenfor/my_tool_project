#!/usr/bin/env node
/**
 * 全库增量流程：sync-all → inventory → optimize → diff → push
 */
import { spawnSync } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';
import { getYuqueRoot } from './lib/env.mjs';

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
const dryRun = args.includes('--dry-run');
const skipPush = args.includes('--skip-push');
const fullSync = args.includes('--full');
const offline = args.includes('--offline');
const singleRepo = args.includes('--single-repo');

console.log(`\n🔄 语雀全库增量流程（数据目录: ${getYuqueRoot()}）\n`);

if (!offline) {
  const syncArgs = singleRepo
    ? fullSync
      ? ['--full']
      : []
    : fullSync
      ? ['--all', '--full']
      : ['--all'];
  const syncRes = spawnSync('node', [path.join(__dirname, 'sync.mjs'), ...syncArgs], {
    cwd: ROOT,
    stdio: 'inherit',
  });
  if (syncRes.status !== 0) {
    console.warn('⚠️  同步跳过（需配置 .env.local Cookie）。继续使用本地镜像...\n');
  }
} else {
  console.log('⏭️  离线模式，跳过 sync\n');
}

run('build-inventory.mjs');
run('backup.mjs');
run('optimize-rules.mjs', dryRun ? ['--dry-run'] : []);
run('generate-diff.mjs');

if (!skipPush && !dryRun) {
  run('push-all.mjs', ['--dry-run']);
  console.log('\n预览完成后执行: npm run push');
} else {
  console.log('\n✅ 流程完成（未写回）');
}
