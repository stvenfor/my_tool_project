#!/usr/bin/env node
/**
 * 删除语雀云端重复/孤儿文档（保留本地 inventory 中已有 slug 的版本）。
 *
 * npm run cleanup-cloud -- 金融           # dry-run
 * npm run cleanup-cloud -- 金融 --execute # 实际删除
 */
import fs from 'fs';
import path from 'path';
import { META_DIR, REPORTS_DIR, ensureDirs, loadEnvLocal } from './lib/env.mjs';
import {
  checkWebSession,
  closeBrowserContext,
  deleteDocWeb,
  getDocWeb,
  useWebPush,
} from './lib/yuque-web-api.mjs';

const BOOK_SLUG_MAP = {
  金融: 'xk57o3',
  project: 'eav1v0',
  默认知识库: 'xd5v9h',
};

function resolveBookSlug(book) {
  return BOOK_SLUG_MAP[book] || book;
}

function loadLocalSlugs(book) {
  const { documents } = JSON.parse(
    fs.readFileSync(path.join(META_DIR, 'inventory.json'), 'utf8'),
  );
  return new Set(documents.filter(d => d.book === book && d.slug).map(d => d.slug));
}

function loadDeleteCandidates(book) {
  const reportPath = path.join(REPORTS_DIR, `audit-${book}.json`);
  if (!fs.existsSync(reportPath)) {
    throw new Error(`未找到 ${reportPath}，请先运行: npm run audit-book -- ${book}`);
  }
  const report = JSON.parse(fs.readFileSync(reportPath, 'utf8'));
  const localSlugs = loadLocalSlugs(book);
  const toDelete = [];

  for (const item of report.cloud_only || []) {
    if (!localSlugs.has(item.slug)) {
      toDelete.push(item);
    }
  }

  for (const dup of report.duplicate_titles || []) {
    for (const slug of dup.slugs) {
      if (!localSlugs.has(slug) && !toDelete.some(d => d.slug === slug)) {
        toDelete.push({ title: dup.title, slug, url: dup.urls?.[dup.slugs.indexOf(slug)] });
      }
    }
  }

  return toDelete;
}

async function main() {
  ensureDirs();
  const args = process.argv.slice(2);
  const book = args.find(a => !a.startsWith('--'));
  const execute = args.includes('--execute');

  if (!book) {
    console.error('用法: npm run cleanup-cloud -- 金融 [--execute]');
    process.exit(1);
  }

  if (!useWebPush(loadEnvLocal())) {
    console.error('cleanup-cloud 需要浏览器 Cookie 模式');
    process.exit(1);
  }

  const session = await checkWebSession();
  if (!session.ok) {
    throw new Error('浏览器登录态无效，请运行 npm run export-cookie');
  }

  const group = 'hanshihuanyan';
  const bookSlug = resolveBookSlug(book);
  const localSlugs = loadLocalSlugs(book);
  const candidates = loadDeleteCandidates(book);

  console.log(`\n🧹 清理云端重复: ${book} (${group}/${bookSlug})`);
  console.log(`   本地 slug 数: ${localSlugs.size}`);
  console.log(`   待删除: ${candidates.length} 篇 (${execute ? '执行' : 'dry-run'})\n`);

  if (candidates.length === 0) {
    console.log('✅ 无需清理');
    await closeBrowserContext();
    return;
  }

  const results = [];
  for (const item of candidates) {
    const remote = await getDocWeb(group, bookSlug, item.slug);
    if (!remote.ok) {
      console.log(`⏭️  ${item.title} (${item.slug}) — 已不存在 HTTP ${remote.status}`);
      results.push({ ...item, status: 'skipped', reason: `HTTP ${remote.status}` });
      continue;
    }

    const docId = remote.data?.id;
    if (!docId) {
      console.log(`❌ ${item.title} (${item.slug}) — 无法获取 doc id`);
      results.push({ ...item, status: 'failed', reason: 'no doc id' });
      continue;
    }

    if (!execute) {
      console.log(`🔍 将删除: ${item.title} (${item.slug}) id=${docId}`);
      results.push({ ...item, status: 'dry-run', docId });
      continue;
    }

    const del = await deleteDocWeb(docId);
    if (del.ok) {
      console.log(`✅ 已删除: ${item.title} (${item.slug})`);
      results.push({ ...item, status: 'deleted', docId });
    } else {
      console.log(`❌ 删除失败: ${item.title} HTTP ${del.status}`);
      results.push({ ...item, status: 'failed', reason: `HTTP ${del.status}`, docId });
    }
  }

  const logPath = path.join(REPORTS_DIR, `cleanup-${book}.json`);
  fs.writeFileSync(
    logPath,
    JSON.stringify({ at: new Date().toISOString(), book, execute, results }, null, 2),
  );
  console.log(`\n✅ 日志: ${logPath}`);
  if (!execute) {
    console.log('   确认无误后: npm run cleanup-cloud -- 金融 --execute');
  }
  await closeBrowserContext();
}

main().catch(err => {
  console.error(`❌ ${err.message}`);
  closeBrowserContext().finally(() => process.exit(1));
});
