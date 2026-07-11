#!/usr/bin/env node
/**
 * 从本地语雀镜像导出知识库到 _migrate/export/<book>/
 * 结构：docs/ markdown, assets/ 图片, attachments/ 附件, manifest.json
 */
import fs from 'fs';
import path from 'path';
import {
  bookExportDir,
  ensureMigrateDirs,
  EXPORT_DIR,
  getInventory,
  writeJson,
} from './lib/paths.mjs';
import { safeFileBase } from './lib/safe-name.mjs';
import { ROOT, getYuqueRoot, listRepoMirrorDirs, loadEnvLocal } from '../lib/env.mjs';

const ASSET_DIR_NAMES = new Set(['img', 'assets', '_assets']);
const ATTACHMENT_DIR_NAMES = new Set(['attachments', 'attachment', 'files']);

function readMetaSidecar(absPath) {
  const metaPath = absPath.replace(/\.md$/, '.meta.json');
  if (!fs.existsSync(metaPath)) return null;
  try {
    return JSON.parse(fs.readFileSync(metaPath, 'utf8'));
  } catch {
    return null;
  }
}

function extractYuqueUrl(content) {
  const match = content.match(
    /(?:原文|迁移来源)[：:]\s*<?(https?:\/\/(?:www\.)?yuque\.com\/[^>\s)]+)>?/,
  );
  return match ? match[1] : null;
}

function extractTitle(content, filename) {
  const h1 = content.match(/^#\s+(.+)$/m);
  if (h1) return h1[1].trim();
  const base = path.basename(filename, '.md');
  return base === 'index' ? null : base;
}

function walkMarkdown(mirrorDir) {
  const results = [];
  function walk(dir, rel = '') {
    if (!fs.existsSync(dir)) return;
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (entry.name.startsWith('.')) continue;
      const full = path.join(dir, entry.name);
      const relPath = rel ? `${rel}/${entry.name}` : entry.name;
      if (entry.isDirectory()) {
        if (ASSET_DIR_NAMES.has(entry.name) || ATTACHMENT_DIR_NAMES.has(entry.name)) {
          continue;
        }
        walk(full, relPath);
      } else if (entry.isFile() && entry.name.endsWith('.md')) {
        results.push({ absPath: full, relPath, folderPath: rel });
      }
    }
  }
  walk(mirrorDir);
  return results;
}

function copyAssetTree(srcRoot, destRoot) {
  let count = 0;
  function walk(dir, rel = '') {
    if (!fs.existsSync(dir)) return;
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      const relPath = rel ? `${rel}/${entry.name}` : entry.name;
      if (entry.isDirectory()) {
        walk(full, relPath);
      } else if (entry.isFile()) {
        const dest = path.join(destRoot, relPath);
        fs.mkdirSync(path.dirname(dest), { recursive: true });
        fs.copyFileSync(full, dest);
        count += 1;
      }
    }
  }
  walk(srcRoot);
  return count;
}

function collectAssetDirs(mirrorDir) {
  const dirs = [];
  function walk(dir, rel = '') {
    if (!fs.existsSync(dir)) return;
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (!entry.isDirectory()) continue;
      const full = path.join(dir, entry.name);
      const relPath = rel ? `${rel}/${entry.name}` : entry.name;
      if (ASSET_DIR_NAMES.has(entry.name)) {
        dirs.push({ src: full, rel: relPath, kind: 'assets' });
      } else if (ATTACHMENT_DIR_NAMES.has(entry.name)) {
        dirs.push({ src: full, rel: relPath, kind: 'attachments' });
      } else {
        walk(full, relPath);
      }
    }
  }
  walk(mirrorDir);
  return dirs;
}

function exportBook(book, mirrorDir, inventoryDocs, pilotPaths = null) {
  const exportRoot = bookExportDir(book);
  const docsDir = path.join(exportRoot, 'docs');
  fs.rmSync(exportRoot, { recursive: true, force: true });
  fs.mkdirSync(docsDir, { recursive: true });

  const invByRel = new Map(
    inventoryDocs.filter(d => d.book === book).map(d => [d.rel_path.replace(`${book}/`, ''), d]),
  );

  const manifestDocs = [];
  const mdFiles = walkMarkdown(mirrorDir);

  for (const { absPath, relPath, folderPath } of mdFiles) {
    const fullRel = `${book}/${relPath}`;
    if (pilotPaths && !pilotPaths.has(fullRel)) continue;
    const content = fs.readFileSync(absPath, 'utf8');
    const meta = readMetaSidecar(absPath);
    const inv = invByRel.get(relPath) || invByRel.get(`${book}/${relPath}`);
    const title =
      meta?.title ||
      inv?.title ||
      extractTitle(content, relPath) ||
      path.basename(relPath, '.md');
    const slug = meta?.slug || inv?.slug || null;
    const group = meta?.group || inv?.group || 'hanshihuanyan';
    const bookSlug = meta?.book_slug || inv?.book_slug || book;
    const yuqueUrl =
      extractYuqueUrl(content) ||
      (slug ? `https://www.yuque.com/${group}/${bookSlug}/${slug}` : null);

    const safeName = safeFileBase(title);
    const destRel = folderPath ? `${folderPath}/${safeName}` : safeName;
    const destAbs = path.join(docsDir, destRel);
    fs.mkdirSync(path.dirname(destAbs), { recursive: true });
    fs.copyFileSync(absPath, destAbs);

    manifestDocs.push({
      title,
      slug,
      yuque_url: yuqueUrl,
      source_rel_path: relPath,
      folder_path: folderPath === '.' ? '' : folderPath,
      export_rel_path: `docs/${destRel}`,
      safe_filename: safeName,
      group,
      book_slug: bookSlug,
    });
  }

  let assetCount = 0;
  let attachmentCount = 0;
  for (const { src, rel, kind } of collectAssetDirs(mirrorDir)) {
    const destKind = kind === 'attachments' ? 'attachments' : 'assets';
    const destRoot = path.join(exportRoot, destKind, rel);
    const copied = copyAssetTree(src, destRoot);
    if (kind === 'attachments') attachmentCount += copied;
    else assetCount += copied;
  }

  const manifest = {
    book,
    book_slug: manifestDocs[0]?.book_slug || book,
    group: manifestDocs[0]?.group || 'hanshihuanyan',
    exported_at: new Date().toISOString(),
    source_mirror: mirrorDir,
    stats: {
      documents: manifestDocs.length,
      assets: assetCount,
      attachments: attachmentCount,
    },
    documents: manifestDocs.sort((a, b) => a.export_rel_path.localeCompare(b.export_rel_path, 'zh-CN')),
  };

  writeJson(path.join(exportRoot, 'manifest.json'), manifest);
  return manifest;
}

function main() {
  ensureMigrateDirs();
  const args = process.argv.slice(2);
  const bookFilter = args.find(a => a.startsWith('--book='))?.split('=')[1];
  const limit = Number(args.find(a => a.startsWith('--limit='))?.split('=')[1] || 0);
  const pilotListPath =
    args.find(a => a.startsWith('--pilot-list='))?.split('=')[1] ||
    path.join(ROOT, '_migrate/pilot-docs.json');
  const usePilotList = args.includes('--pilot') || args.includes('--pilot-list');

  const env = loadEnvLocal();
  const yuqueRoot = getYuqueRoot(env);
  let repos = listRepoMirrorDirs(env);

  let pilotPaths = null;
  if (usePilotList && fs.existsSync(pilotListPath)) {
    pilotPaths = new Set(JSON.parse(fs.readFileSync(pilotListPath, 'utf8')));
    const pilotBooks = [...new Set([...pilotPaths].map(p => p.split('/')[0]))];
    repos = repos.filter(r => pilotBooks.includes(r.book));
    console.log(`🎯 试点模式: ${pilotPaths.size} 篇文档 (${pilotBooks.join(', ')})`);
  } else {
    const inventory = getInventory();
    const allowed = new Set(inventory.repos || []);
    repos = repos.filter(r => allowed.has(r.book));
    if (bookFilter) repos = repos.filter(r => r.book === bookFilter);
  }
  if (repos.length === 0) {
    console.error('未找到可导出的知识库镜像');
    process.exit(1);
  }

  const inventory = getInventory();
  const exported = [];

  for (const { book, mirrorDir } of repos) {
    console.log(`📦 导出知识库: ${book}`);
    let manifest = exportBook(book, mirrorDir, inventory.documents || [], pilotPaths);
    if (!pilotPaths && limit > 0 && manifest.documents.length > limit) {
      const selected = manifest.documents.slice(0, limit);
      const exportRoot = bookExportDir(book);
      const keepPaths = new Set(selected.map(d => d.export_rel_path));
      for (const doc of manifest.documents) {
        if (!keepPaths.has(doc.export_rel_path)) {
          const abs = path.join(exportRoot, doc.export_rel_path);
          if (fs.existsSync(abs)) fs.unlinkSync(abs);
        }
      }
      manifest = { ...manifest, documents: selected, stats: { ...manifest.stats, documents: selected.length } };
      writeJson(path.join(exportRoot, 'manifest.json'), manifest);
    }
    exported.push({ book, ...manifest.stats });
    console.log(`   文档 ${manifest.stats.documents}，图片 ${manifest.stats.assets}，附件 ${manifest.stats.attachments}`);
  }

  writeJson(path.join(EXPORT_DIR, 'export-summary.json'), {
    exported_at: new Date().toISOString(),
    yuque_root: yuqueRoot,
    books: exported,
  });
  console.log(`\n✅ 导出完成 → ${EXPORT_DIR}`);
}

main();
