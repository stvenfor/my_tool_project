#!/usr/bin/env node
/**
 * 对比本地镜像与语雀云端文档，找出重复标题、云端孤儿、本地 404。
 *
 * npm run audit-book -- 金融
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import {
  META_DIR,
  REPORTS_DIR,
  ensureDirs,
  getYuqueRoot,
  loadEnvLocal,
} from './lib/env.mjs';
import {
  checkWebSession,
  closeBrowserContext,
  getDocWeb,
  resolveBookId,
  useWebPush,
} from './lib/yuque-web-api.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');

const BOOK_SLUG_MAP = {
  金融: 'xk57o3',
  project: 'eav1v0',
  默认知识库: 'xd5v9h',
};

function resolveBookSlug(book) {
  return BOOK_SLUG_MAP[book] || book;
}

function loadLocalDocs(book) {
  const inventoryPath = path.join(META_DIR, 'inventory.json');
  if (!fs.existsSync(inventoryPath)) {
    throw new Error('未找到 inventory.json，请先运行 npm run inventory');
  }
  const { documents } = JSON.parse(fs.readFileSync(inventoryPath, 'utf8'));
  return documents.filter(d => d.book === book);
}

async function fetchRemoteDocs(group, bookSlug) {
  const bookId = await resolveBookId(group, bookSlug);
  const { getBrowserContext } = await import('./lib/yuque-web-api.mjs');
  const ctx = await getBrowserContext();
  const page = ctx.pages()[0] || (await ctx.newPage());
  await page.goto(`https://www.yuque.com/${group}/${bookSlug}`, {
    waitUntil: 'domcontentloaded',
    timeout: 60000,
  }).catch(() => {});

  const result = await page.evaluate(async id => {
    const docs = [];
    let offset = 0;
    const limit = 100;
    for (;;) {
      const res = await fetch(
        `/api/docs?book_id=${id}&offset=${offset}&limit=${limit}&optional_properties=tags`,
      );
      const json = await res.json().catch(() => ({}));
      const batch = json.data || [];
      docs.push(...batch);
      if (batch.length < limit) break;
      offset += limit;
    }
    return docs.map(d => ({
      id: d.id,
      slug: d.slug,
      title: d.title,
      updated_at: d.updated_at,
    }));
  }, bookId);

  return result;
}

function groupByTitle(docs) {
  const map = {};
  for (const d of docs) {
    const key = (d.title || '').trim();
    if (!key) continue;
    map[key] = map[key] || [];
    map[key].push(d);
  }
  return Object.entries(map).filter(([, items]) => items.length > 1);
}

async function main() {
  ensureDirs();
  const book = process.argv.slice(2).find(a => !a.startsWith('--'));
  if (!book) {
    console.error('用法: npm run audit-book -- 金融');
    process.exit(1);
  }

  const env = loadEnvLocal();
  if (!useWebPush(env)) {
    console.error('audit-book 需要浏览器 Cookie 模式（无 Personal Token）');
    process.exit(1);
  }

  const session = await checkWebSession();
  if (!session.ok) {
    throw new Error(`浏览器登录态无效，请运行 npm run export-cookie`);
  }

  const group = 'hanshihuanyan';
  const bookSlug = resolveBookSlug(book);
  const localDocs = loadLocalDocs(book);
  const localSlugs = new Set(localDocs.map(d => d.slug).filter(Boolean));
  const localTitles = new Map(localDocs.map(d => [d.title, d.rel_path]));

  console.log(`\n🔍 审计知识库: ${book} (${group}/${bookSlug})`);
  console.log(`   本地文档: ${localDocs.length} 篇\n`);

  const remoteDocs = await fetchRemoteDocs(group, bookSlug);
  console.log(`   云端文档: ${remoteDocs.length} 篇\n`);

  const dupTitles = groupByTitle(remoteDocs);
  const cloudOnly = remoteDocs.filter(d => !localSlugs.has(d.slug));
  const local404 = [];

  for (const doc of localDocs.filter(d => d.slug)) {
    const remote = await getDocWeb(group, bookSlug, doc.slug);
    if (!remote.ok && remote.status === 404) {
      local404.push(doc);
    }
  }

  const report = {
    generated_at: new Date().toISOString(),
    book,
    book_slug: bookSlug,
    local_count: localDocs.length,
    remote_count: remoteDocs.length,
    duplicate_titles: dupTitles.map(([title, items]) => ({
      title,
      slugs: items.map(i => i.slug),
      urls: items.map(i => `https://www.yuque.com/${group}/${bookSlug}/${i.slug}`),
    })),
    cloud_only: cloudOnly.map(d => ({
      title: d.title,
      slug: d.slug,
      url: `https://www.yuque.com/${group}/${bookSlug}/${d.slug}`,
    })),
    local_404: local404.map(d => ({
      rel_path: d.rel_path,
      slug: d.slug,
      title: d.title,
    })),
  };

  const reportPath = path.join(REPORTS_DIR, `audit-${book}.json`);
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));

  console.log('--- 重复标题（云端） ---');
  if (dupTitles.length === 0) {
    console.log('   无');
  } else {
    for (const [title, items] of dupTitles) {
      console.log(`   「${title}」× ${items.length}`);
      for (const item of items) {
        console.log(`     - ${item.slug}`);
      }
    }
  }

  console.log('\n--- 仅云端存在（本地无 slug 匹配） ---');
  if (cloudOnly.length === 0) {
    console.log('   无');
  } else {
    for (const d of cloudOnly.slice(0, 20)) {
      console.log(`   - ${d.title} (${d.slug})`);
    }
    if (cloudOnly.length > 20) {
      console.log(`   ... 另有 ${cloudOnly.length - 20} 篇`);
    }
  }

  console.log('\n--- 本地有 slug 但云端 404 ---');
  if (local404.length === 0) {
    console.log('   无');
  } else {
    for (const d of local404) {
      console.log(`   - ${d.rel_path}`);
    }
  }

  console.log(`\n✅ 报告: ${reportPath}`);
  await closeBrowserContext();
}

main().catch(err => {
  console.error(`❌ ${err.message}`);
  closeBrowserContext().finally(() => process.exit(1));
});
