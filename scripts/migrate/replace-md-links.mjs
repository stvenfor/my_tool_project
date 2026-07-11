#!/usr/bin/env node
/**
 * 将已导入飞书文档中的相对 .md 内部链接替换为 wiki URL
 */
import { spawnSync } from 'child_process';
import fs from 'fs';
import path from 'path';
import { bookCleanDir, readJson, statePath, writeJson } from './lib/paths.mjs';
import { ROOT } from '../lib/env.mjs';

const MD_LINK_RE = /(?<!!)\[([^\]]*)\]\(([^)]+)\)/g;

function runLark(args) {
  const result = spawnSync('lark-cli', args, { encoding: 'utf8', cwd: ROOT });
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
    const keys = new Set([
      doc.source_rel_path,
      doc.export_rel_path.replace(/^docs\//, ''),
      doc.folder_path ? `${doc.folder_path}/${doc.safe_filename}` : doc.safe_filename,
      doc.safe_filename,
      path.basename(doc.source_rel_path),
    ]);
    for (const key of keys) {
      if (key) map.set(key.replace(/\\/g, '/'), info.lark_url);
    }
  }
  return map;
}

function resolveMdLink(linkTarget, docFolderPath, pathMap) {
  if (/^https?:\/\//i.test(linkTarget) || linkTarget.startsWith('#')) return null;
  let target = linkTarget.split('#')[0];
  if (!target.endsWith('.md')) return null;
  target = target.replace(/^\.\//, '');

  const candidates = [];
  if (docFolderPath) {
    candidates.push(path.posix.normalize(`${docFolderPath}/${target}`));
  }
  candidates.push(path.posix.normalize(target));
  candidates.push(path.posix.basename(target));

  for (const c of candidates) {
    if (pathMap.has(c)) return pathMap.get(c);
  }
  return null;
}

function replaceLinks(content, docFolderPath, pathMap) {
  const unreplaced = [];
  const replaced = content.replace(MD_LINK_RE, (full, text, href) => {
    const larkUrl = resolveMdLink(href, docFolderPath, pathMap);
    if (larkUrl) return `[${text}](${larkUrl})`;
    if (href.endsWith('.md') && !href.startsWith('http')) {
      unreplaced.push(href);
    }
    return full;
  });
  return { content: replaced, unreplaced: [...new Set(unreplaced)] };
}

function processBook(book) {
  const cleanRoot = bookCleanDir(book);
  const manifest = readJson(path.join(cleanRoot, 'manifest.json'));
  const importState = readJson(statePath(`import-${book}.json`), { imported: {} });
  const pathMap = buildPathMap(manifest, importState);
  const report = { replaced: [], unreplaced: [] };

  for (const doc of manifest.documents) {
    const info = importState.imported[doc.yuque_url];
    if (!info?.doc_token) continue;

    const fetch = runLark([
      'docs',
      '+fetch',
      '--as',
      'user',
      '--doc',
      info.doc_token,
      '--doc-format',
      'markdown',
      '--format',
      'json',
    ]);
    const md =
      fetch.data?.content ||
      fetch.data?.markdown ||
      fetch.data?.data?.content ||
      fetch.data?.document?.content ||
      '';
    if (!md) {
      report.unreplaced.push({ title: doc.title, reason: 'fetch_failed' });
      continue;
    }

    const { content, unreplaced } = replaceLinks(md, doc.folder_path, pathMap);
    if (content === md) continue;

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
      content,
      '--format',
      'json',
    ]);

    if (updated.ok) {
      report.replaced.push({ title: doc.title, count: unreplaced.length });
      console.log(`🔗 ${doc.title}: 已替换相对链接`);
    } else {
      report.unreplaced.push({
        title: doc.title,
        reason: 'update_failed',
        links: unreplaced,
      });
    }
    if (unreplaced.length) {
      report.unreplaced.push({ title: doc.title, links: unreplaced });
    }
  }

  writeJson(path.join(cleanRoot, 'md-link-replace-report.json'), report);
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
    console.log(`\n📎 处理 ${book} 相对链接...`);
    const report = processBook(book);
    console.log(`   更新 ${report.replaced.length} 篇，未替换 ${report.unreplaced.length} 条`);
  }
}

main();
