#!/usr/bin/env node
/**
 * 同步入口：有 YUQUE_PERSONAL_TOKEN 时走 API，否则走 yuque-dl + Cookie
 */
import { spawnSync } from 'child_process';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import {
  META_DIR,
  ROOT,
  ensureDirs,
  getPersonalToken,
  getRepoConfig,
  getSessionValue,
  getYuqueRoot,
  loadEnvLocal,
  validateYuqueAuth,
} from './lib/env.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const forceFull = args.includes('--full');
const syncAll = args.includes('--all');
const dryRun = args.includes('--dry-run');

function runYuqueDl(cmdArgs) {
  if (dryRun) {
    console.log(`   [dry-run] npx yuque-dl ${cmdArgs.join(' ')}`);
    return 0;
  }
  const result = spawnSync('npx', ['yuque-dl', ...cmdArgs], {
    cwd: ROOT,
    stdio: 'inherit',
    env: { ...process.env },
  });
  return result.status ?? 1;
}

function appendSyncLog(entry) {
  const syncLogPath = path.join(META_DIR, 'sync-log.json');
  const prev = fs.existsSync(syncLogPath)
    ? JSON.parse(fs.readFileSync(syncLogPath, 'utf8'))
    : { runs: [] };
  prev.runs.push(entry);
  prev.lastSync = new Date().toISOString();
  fs.writeFileSync(syncLogPath, JSON.stringify(prev, null, 2));
}

function runPostSyncIndex() {
  const inventoryRes = spawnSync('node', [path.join(__dirname, 'build-inventory.mjs')], {
    cwd: ROOT,
    stdio: 'inherit',
  });
  if (inventoryRes.status !== 0) {
    console.warn('⚠️  inventory 生成失败，请手动运行 npm run inventory');
    return;
  }
  const reconcileRes = spawnSync('node', [path.join(__dirname, 'reconcile-meta.mjs')], {
    cwd: ROOT,
    stdio: 'inherit',
  });
  if (reconcileRes.status !== 0) {
    console.warn('⚠️  meta 对账失败，请手动运行 npm run reconcile-meta');
  }
}

function main() {
  ensureDirs();
  const env = loadEnvLocal();

  if (getPersonalToken(env)) {
    const res = spawnSync('node', [path.join(__dirname, 'sync-api.mjs'), ...args], {
      cwd: ROOT,
      stdio: 'inherit',
      env: { ...process.env },
    });
    if (res.status === 0) {
      console.log('✅ API 同步完成，正在更新清单与时间戳...');
      runPostSyncIndex();
    }
    process.exit(res.status ?? 1);
  }

  const authError = validateYuqueAuth(env);
  if (authError) {
    console.error(`❌ ${authError}`);
    process.exit(1);
  }
  const sessionValue = getSessionValue(env);

  const yuqueRoot = getYuqueRoot(env);
  fs.mkdirSync(yuqueRoot, { recursive: true });

  if (syncAll) {
    const cmdArgs = ['user', '-d', yuqueRoot, '-t', sessionValue, '--toc'];
    if (!forceFull) cmdArgs.push('--incremental');

    console.log(`📥 同步账号下所有知识库 → ${yuqueRoot}`);
    const status = runYuqueDl(cmdArgs);
    if (status !== 0) {
      console.error('❌ yuque-dl 全量同步失败');
      process.exit(status);
    }
    appendSyncLog({
      at: new Date().toISOString(),
      mode: forceFull ? 'full-all' : 'incremental-all',
      yuqueRoot,
    });
    console.log('✅ 同步完成，正在更新清单与时间戳...');
    runPostSyncIndex();
  } else {
    const { repoUrl, book, mirrorDir } = getRepoConfig(env);
    fs.mkdirSync(mirrorDir, { recursive: true });

    const cmdArgs = [repoUrl, '-d', mirrorDir, '-t', sessionValue, '--toc'];
    if (!forceFull) cmdArgs.push('--incremental');

    console.log(`📥 同步知识库: ${repoUrl}`);
    console.log(`   输出目录: ${mirrorDir}`);
    const status = runYuqueDl(cmdArgs);
    if (status !== 0) {
      console.error('❌ yuque-dl 同步失败');
      process.exit(status);
    }
    appendSyncLog({
      at: new Date().toISOString(),
      repoUrl,
      book,
      mode: forceFull ? 'full' : 'incremental',
      mirrorDir,
      yuqueRoot,
    });
    console.log('✅ 同步完成，正在更新清单与时间戳...');
    runPostSyncIndex();
  }
}

main();
