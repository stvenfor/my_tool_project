#!/usr/bin/env node
/**
 * 从云端刷新 .meta.json 中的 remote_updated_at，修复同步后时间戳陈旧问题。
 *
 * npm run reconcile-meta
 * npm run reconcile-meta -- --book=金融
 */
import fs from 'fs';
import path from 'path';
import {
  META_DIR,
  ensureDirs,
  getRepoConfig,
  loadEnvLocal,
  resolveDocAbsPath,
} from './lib/env.mjs';
import { getDoc, sleep } from './lib/yuque-api.mjs';
import {
  checkWebSession,
  closeBrowserContext,
  getDocWeb,
  useWebPush,
} from './lib/yuque-web-api.mjs';

function loadInventory() {
  const inventoryPath = path.join(META_DIR, 'inventory.json');
  if (!fs.existsSync(inventoryPath)) {
    throw new Error('未找到 inventory.json，请先运行 npm run inventory');
  }
  return JSON.parse(fs.readFileSync(inventoryPath, 'utf8'));
}

async function fetchRemoteUpdatedAt(doc, webPush) {
  const bookSlug = doc.book_slug || doc.book;
  if (webPush) {
    const res = await getDocWeb(doc.group, bookSlug, doc.slug);
    return { ok: res.ok, status: res.status, updatedAt: res.data?.updated_at };
  }
  const res = await getDoc(doc.group, bookSlug, doc.slug);
  return {
    ok: res.ok,
    status: res.status,
    updatedAt: res.data?.data?.updated_at,
  };
}

async function main() {
  ensureDirs();
  const args = process.argv.slice(2);
  const bookFilter = args.find(a => a.startsWith('--book='))?.split('=')[1];
  const env = loadEnvLocal();
  const webPush = useWebPush(env);

  if (webPush) {
    const session = await checkWebSession();
    if (!session.ok) {
      throw new Error(`浏览器登录态无效，请运行 npm run get-token`);
    }
    console.log(`🔐 对账模式: Web API (${session.login})`);
  } else {
    console.log('🔐 对账模式: v2 API');
  }

  const { documents } = loadInventory();
  let targets = documents.filter(d => d.slug);
  if (bookFilter) {
    targets = targets.filter(d => d.book === bookFilter);
  }

  let updated = 0;
  let failed = 0;

  try {
    for (const doc of targets) {
      const absPath = resolveDocAbsPath(doc, env);
      const metaPath = absPath.replace(/\.md$/, '.meta.json');
      if (!fs.existsSync(metaPath)) continue;

      const remote = await fetchRemoteUpdatedAt(doc, webPush);
      if (!remote.ok || !remote.updatedAt) {
        failed += 1;
        console.log(`❌ ${doc.rel_path} — HTTP ${remote.status}`);
        await sleep(webPush ? 220 : 120);
        continue;
      }

      const meta = JSON.parse(fs.readFileSync(metaPath, 'utf8'));
      if (meta.remote_updated_at === remote.updatedAt) {
        console.log(`⏭️  ${doc.rel_path}`);
      } else {
        meta.remote_updated_at = remote.updatedAt;
        meta.last_reconciled_at = new Date().toISOString();
        fs.writeFileSync(metaPath, JSON.stringify(meta, null, 2));
        updated += 1;
        console.log(`✅ ${doc.rel_path}`);
      }
      await sleep(webPush ? 220 : 120);
    }
  } finally {
    if (webPush) await closeBrowserContext();
  }

  console.log(`\n✅ 对账完成: 更新 ${updated}，失败 ${failed}，跳过 ${targets.length - updated - failed}`);
  if (failed > 0) process.exit(1);
}

main().catch(err => {
  console.error(`❌ ${err.message}`);
  process.exit(1);
});
