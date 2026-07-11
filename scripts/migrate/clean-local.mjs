#!/usr/bin/env node
/**
 * 清洗导出的 Markdown：修复图片路径、追加迁移来源、记录异常
 */
import fs from 'fs';
import path from 'path';
import {
  bookCleanDir,
  bookExportDir,
  CLEAN_DIR,
  ensureMigrateDirs,
  EXPORT_DIR,
  readJson,
  writeJson,
} from './lib/paths.mjs';

const IMG_RE = /!\[([^\]]*)\]\(([^)]+)\)/g;
const LINK_RE = /(?<!!)\[([^\]]*)\]\(([^)]+)\)/g;
const YUQUE_URL_RE = /https?:\/\/(?:www\.)?yuque\.com\/[^\s)>\]]+/g;
const EXISTING_FOOTER_RE = /\n---\n\n迁移来源：[^\n]+\s*$/;

function findAssetFile(exportRoot, imgPath) {
  const rel = imgPath.replace(/^\.\//, '');
  const basename = path.basename(rel);
  const assetsRoot = path.join(exportRoot, 'assets');
  if (!fs.existsSync(assetsRoot)) return null;

  const direct = [
    path.join(exportRoot, rel),
    path.join(assetsRoot, rel),
    path.join(assetsRoot, rel.replace(/^img\//, '')),
  ];
  for (const abs of direct) {
    if (fs.existsSync(abs)) return abs;
  }

  function walk(dir) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        const found = walk(full);
        if (found) return found;
      } else if (entry.name === basename) {
        return full;
      }
    }
    return null;
  }
  return walk(assetsRoot);
}

function normalizeImagePath(rawPath, docDir, exportRoot) {
  if (/^https?:\/\//i.test(rawPath)) {
    return { path: rawPath, issue: 'remote_image_url' };
  }

  const abs = findAssetFile(exportRoot, rawPath);
  if (abs) {
    const rel = path.relative(docDir, abs).split(path.sep).join('/');
    return { path: rel.startsWith('.') ? rel : `./${rel}`, issue: null, abs };
  }

  return { path: rawPath, issue: 'missing_asset' };
}

function stageDocAssets(docDir, exportRoot, content) {
  const staged = new Set();
  for (const match of content.matchAll(IMG_RE)) {
    const imgPath = match[2];
    const { abs, issue } = normalizeImagePath(imgPath, docDir, exportRoot);
    if (issue || !abs) continue;
    const rel = imgPath.replace(/^\.\//, '');
    const dest = path.join(docDir, rel);
    if (staged.has(dest)) continue;
    staged.add(dest);
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    fs.copyFileSync(abs, dest);
  }
}

function cleanMarkdown(content, docAbsPath, exportRoot, yuqueUrl) {
  const issues = [];
  const docDir = path.dirname(docAbsPath);

  stageDocAssets(docDir, exportRoot, content);

  let cleaned = content.replace(IMG_RE, (full, alt, imgPath) => {
    if (/^https?:\/\//i.test(imgPath)) {
      issues.push({ type: 'remote_image_url', detail: imgPath });
      return full;
    }
    const rel = imgPath.replace(/^\.\//, '');
    const local = path.join(docDir, rel);
    if (fs.existsSync(local)) {
      return `![${alt}](./${rel.split(path.sep).join('/')})`;
    }
    const found = findAssetFile(exportRoot, imgPath);
    if (found) {
      const staged = path.join(docDir, rel);
      fs.mkdirSync(path.dirname(staged), { recursive: true });
      fs.copyFileSync(found, staged);
      return `![${alt}](./${rel.split(path.sep).join('/')})`;
    }
    issues.push({ type: 'missing_asset', detail: imgPath });
    return full;
  });

  cleaned = cleaned.replace(EXISTING_FOOTER_RE, '');

  if (yuqueUrl && !cleaned.includes('迁移来源：')) {
    cleaned = `${cleaned.trim()}\n\n---\n\n迁移来源：${yuqueUrl}\n`;
  }

  const yuqueLinks = [...cleaned.matchAll(LINK_RE)]
    .map(m => m[2])
    .filter(u => /yuque\.com/i.test(u));

  return { content: cleaned, issues, yuqueLinks };
}

function copyTree(src, dest) {
  if (!fs.existsSync(src)) return;
  fs.mkdirSync(dest, { recursive: true });
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    const s = path.join(src, entry.name);
    const d = path.join(dest, entry.name);
    if (entry.isDirectory()) copyTree(s, d);
    else fs.copyFileSync(s, d);
  }
}

function cleanBook(book) {
  const exportRoot = bookExportDir(book);
  const manifestPath = path.join(exportRoot, 'manifest.json');
  if (!fs.existsSync(manifestPath)) {
    throw new Error(`未找到导出清单: ${manifestPath}，请先运行 export-yuque.mjs`);
  }
  const manifest = readJson(manifestPath);
  const cleanRoot = bookCleanDir(book);
  fs.rmSync(cleanRoot, { recursive: true, force: true });
  fs.mkdirSync(cleanRoot, { recursive: true });

  copyTree(path.join(exportRoot, 'assets'), path.join(cleanRoot, 'assets'));
  copyTree(path.join(exportRoot, 'attachments'), path.join(cleanRoot, 'attachments'));

  const cleanManifest = {
    ...manifest,
    cleaned_at: new Date().toISOString(),
    documents: [],
  };

  const allIssues = [];

  for (const doc of manifest.documents) {
    const srcAbs = path.join(exportRoot, doc.export_rel_path);
    const destAbs = path.join(cleanRoot, doc.export_rel_path);
    fs.mkdirSync(path.dirname(destAbs), { recursive: true });

    const raw = fs.readFileSync(srcAbs, 'utf8');
    const { content, issues, yuqueLinks } = cleanMarkdown(
      raw,
      destAbs,
      exportRoot,
      doc.yuque_url,
    );
    fs.writeFileSync(destAbs, content);

    const docIssues = issues.map(i => ({ ...i, doc: doc.title, export_rel_path: doc.export_rel_path }));
    allIssues.push(...docIssues);

    cleanManifest.documents.push({
      ...doc,
      clean_rel_path: doc.export_rel_path,
      import_file: path.join(cleanRoot, doc.export_rel_path),
      image_issues: issues,
      yuque_internal_links: yuqueLinks,
    });
  }

  writeJson(path.join(cleanRoot, 'manifest.json'), cleanManifest);
  writeJson(path.join(cleanRoot, 'clean-issues.json'), allIssues);
  return { cleanRoot, manifest: cleanManifest, issues: allIssues };
}

function main() {
  ensureMigrateDirs();
  const args = process.argv.slice(2);
  const bookFilter = args.find(a => a.startsWith('--book='))?.split('=')[1];

  if (!fs.existsSync(EXPORT_DIR)) {
    console.error('未找到 _migrate/export，请先运行 export-yuque.mjs');
    process.exit(1);
  }
  const books = fs
    .readdirSync(EXPORT_DIR, { withFileTypes: true })
    .filter(e => e.isDirectory())
    .map(e => e.name);

  let targetBooks = books;
  if (bookFilter) targetBooks = [bookFilter];

  if (targetBooks.length === 0) {
    console.error('未找到已导出的知识库，请先运行 export-yuque.mjs');
    process.exit(1);
  }

  const summary = [];
  for (const book of targetBooks) {
    console.log(`🧹 清洗知识库: ${book}`);
    const { manifest, issues } = cleanBook(book);
    summary.push({
      book,
      documents: manifest.documents.length,
      image_issues: issues.filter(i => i.type === 'missing_asset').length,
      remote_images: issues.filter(i => i.type === 'remote_image_url').length,
    });
    console.log(`   文档 ${manifest.documents.length}，图片异常 ${issues.length}`);
  }

  writeJson(path.join(CLEAN_DIR, 'clean-summary.json'), {
    cleaned_at: new Date().toISOString(),
    books: summary,
  });
  console.log(`\n✅ 清洗完成 → ${CLEAN_DIR}`);
}

main();
