#!/usr/bin/env node
/**
 * 用本地清洗后的 Markdown 覆盖飞书文档（修复导入时丢失的相对链接）
 */
import { spawnSync } from 'child_process';
import fs from 'fs';
import path from 'path';
import { bookCleanDir, readJson, statePath, writeJson } from './lib/paths.mjs';
import { ROOT } from '../lib/env.mjs';

function runLark(args) {
  const result = spawnSync('lark-cli', args, { encoding: 'utf8', cwd: ROOT, maxBuffer: 20 * 1024 * 1024 });
  let data = null;
  try {
    data = result.stdout ? JSON.parse(result.stdout) : null;
  } catch {
    data = { raw: result.stdout };
  }
  return { ok: result.status === 0 && data?.ok !== false, data, stderr: result.stderr, stdout: result.stdout };
}

function buildPathMap(manifest, importState) {
  const map = new Map();
  for (const doc of manifest.documents) {
    const info = importState.imported[doc.yuque_url];
    if (!info?.lark_url) continue;
    const keys = [
      doc.source_rel_path,
      doc.export_rel_path.replace(/^docs\//, ''),
      doc.folder_path ? `${doc.folder_path}/${doc.safe_filename}` : doc.safe_filename,
      doc.safe_filename,
    ].filter(Boolean);
    for (const key of keys) map.set(key.replace(/\\/g, '/'), info.lark_url);
  }
  return map;
}

function resolveMdLink(href, docFolderPath, pathMap) {
  if (/^https?:\/\//i.test(href) || href.startsWith('#')) return href;
  let target = href.split('#')[0];
  const hash = href.includes('#') ? href.slice(href.indexOf('#')) : '';
  if (!target.endsWith('.md')) return href;
  target = target.replace(/^\.\//, '');
  const candidates = [];
  if (docFolderPath) candidates.push(path.posix.normalize(`${docFolderPath}/${target}`));
  candidates.push(path.posix.normalize(target), path.basename(target));
  for (const c of candidates) {
    if (pathMap.has(c)) return pathMap.get(c) + hash;
  }
  return href;
}

function patchLinks(content, docFolderPath, pathMap) {
  return content.replace(/(?<!!)\[([^\]]*)\]\(([^)]+)\)/g, (full, text, href) => {
    const fixed = resolveMdLink(href, docFolderPath, pathMap);
    return `[${text}](${fixed})`;
  });
}

function processBook(book) {
  const cleanRoot = bookCleanDir(book);
  const manifest = readJson(path.join(cleanRoot, 'manifest.json'));
  const importState = readJson(statePath(`import-${book}.json`), { imported: {} });
  const pathMap = buildPathMap(manifest, importState);
  const report = { updated: [], failed: [], skipped: [] };

  for (const doc of manifest.documents) {
    const info = importState.imported[doc.yuque_url];
    if (!info?.doc_token) continue;

    const localPath = path.join(cleanRoot, doc.clean_rel_path);
    if (!fs.existsSync(localPath)) {
      report.skipped.push({ title: doc.title, reason: 'local_missing' });
      continue;
    }

    let content = fs.readFileSync(localPath, 'utf8');
    content = content.replace(/\0/g, '');
    content = patchLinks(content, doc.folder_path, pathMap);

    const stagingPath = path.join(ROOT, '_migrate/staging/refresh', book, `${info.doc_token}.md`);
    fs.mkdirSync(path.dirname(stagingPath), { recursive: true });
    fs.writeFileSync(stagingPath, content);

    const updated = runLark([
      'docs',
      '+update',
      '--as',
      'user',
      '--doc',
      info.doc_token,
      '--command',
      'overwrite',
      '--doc-format',
      'markdown',
      '--content',
      '@' + path.relative(ROOT, stagingPath).split(path.sep).join('/'),
      '--format',
      'json',
    ]);

    if (updated.ok) {
      report.updated.push(doc.title);
      console.log(`   ✅ ${doc.title}`);
    } else {
      report.failed.push({ title: doc.title, error: updated.stderr || updated.stdout });
      console.error(`   ❌ ${doc.title}`);
    }
  }

  writeJson(path.join(cleanRoot, 'content-refresh-report.json'), report);
  return report;
}

function main() {
  const args = process.argv.slice(2);
  const bookFilter = args.find(a => a.startsWith('--book='))?.split('=')[1];
  const cleanDir = path.join(ROOT, '_migrate/clean');
  const books = bookFilter
    ? [bookFilter]
    : fs.readdirSync(cleanDir, { withFileTypes: true }).filter(e => e.isDirectory()).map(e => e.name);

  for (const book of books) {
    console.log(`\n📝 回写 ${book} 本地 Markdown...`);
    const report = processBook(book);
    console.log(`   成功 ${report.updated.length}，失败 ${report.failed.length}`);
  }
}

main();
