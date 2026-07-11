#!/usr/bin/env node
/**
 * 快速扫描云端 Lake 文档是否被 Markdown 写回破坏。
 * npm run scan-corrupted
 * npm run scan-corrupted -- --book=金融
 */
import fs from 'fs';
import path from 'path';
import {
  META_DIR,
  REPORTS_DIR,
  BOOK_SLUG_MAP,
  ensureDirs,
  loadEnvLocal,
} from './lib/env.mjs';
import { sleep } from './lib/yuque-api.mjs';
import {
  checkWebSession,
  closeBrowserContext,
  getDocWeb,
  useWebPush,
} from './lib/yuque-web-api.mjs';

function resolveBookSlug(doc) {
  const bookName = doc.book;
  return BOOK_SLUG_MAP[bookName] || doc.book_slug || bookName;
}

function loadInventory() {
  return JSON.parse(fs.readFileSync(path.join(META_DIR, 'inventory.json'), 'utf8'));
}

function isCorruptedLakeDoc(doc) {
  const format = doc.format || 'lake';
  const body = doc.body || '';
  if (format === 'markdown') return true;
  if (format !== 'lake') return false;
  const isMd = body.trim().startsWith('#');
  const hasLakeHtml = body.includes('lake-content');
  const aslLen = (doc.body_asl || '').length;
  return isMd && !hasLakeHtml && aslLen < 100;
}

async function main() {
  ensureDirs();
  const args = process.argv.slice(2);
  const bookFilter = args.find(a => a.startsWith('--book='))?.split('=')[1];
  const env = loadEnvLocal();

  if (!useWebPush(env)) throw new Error('需要 Cookie 登录');
  const session = await checkWebSession();
  if (!session.ok) throw new Error('登录态无效');

  const { documents } = loadInventory();
  let targets = documents.filter(d => d.slug);
  if (bookFilter) targets = targets.filter(d => d.book === bookFilter);

  const corrupted = [];
  const ok = [];

  try {
    for (let i = 0; i < targets.length; i += 1) {
      const doc = targets[i];
      const bookSlug = resolveBookSlug(doc);
      let remote;
      for (let attempt = 0; attempt < 3; attempt += 1) {
        remote = await getDocWeb(doc.group, bookSlug, doc.slug, { edit: true });
        if (remote.ok) break;
        await sleep(1000 * (attempt + 1));
      }
      if (!remote?.ok) {
        console.warn(`⚠️  跳过 ${doc.rel_path}: HTTP ${remote?.status}`);
        continue;
      }
      if (isCorruptedLakeDoc(remote.data)) corrupted.push(doc.rel_path);
      else ok.push(doc.rel_path);
      if ((i + 1) % 50 === 0) {
        console.log(`   已扫描 ${i + 1}/${targets.length}...`);
      }
      await sleep(120);
    }
  } finally {
    await closeBrowserContext();
  }

  const report = {
    scanned_at: new Date().toISOString(),
    book_filter: bookFilter || null,
    total: targets.length,
    corrupted_count: corrupted.length,
    ok_count: ok.length,
    corrupted,
  };

  const outPath = path.join(REPORTS_DIR, 'corrupted-docs.json');
  fs.writeFileSync(outPath, JSON.stringify(report, null, 2));

  console.log(`✅ 扫描完成: ${targets.length} 篇，损坏 ${corrupted.length} 篇`);
  console.log(`   报告: ${outPath}`);
  if (corrupted.length) {
    console.log('\n损坏文档:');
    for (const p of corrupted.slice(0, 20)) console.log(`  - ${p}`);
    if (corrupted.length > 20) console.log(`  ... 另有 ${corrupted.length - 20} 篇`);
    console.log('\n修复: npm run restore-cloud -- --fix-corrupted');
  }
}

main().catch(err => {
  console.error(`❌ ${err.message}`);
  process.exit(1);
});
