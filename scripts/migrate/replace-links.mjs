#!/usr/bin/env node
/**
 * 批量替换文档中的语雀内部链接为飞书链接（需先完成导入并生成 url-map.json）
 */
import fs from 'fs';
import path from 'path';
import { spawnSync } from 'child_process';
import {
  bookCleanDir,
  readJson,
  statePath,
  URL_MAP_PATH,
  writeJson,
} from './lib/paths.mjs';

const YUQUE_LINK_RE = /https?:\/\/(?:www\.)?yuque\.com\/[^\s)>\]"']+/g;

function runLark(args) {
  const result = spawnSync('lark-cli', args, { encoding: 'utf8' });
  let data = null;
  try {
    data = result.stdout ? JSON.parse(result.stdout) : null;
  } catch {
    data = { raw: result.stdout };
  }
  return { ok: result.status === 0, data, stderr: result.stderr, stdout: result.stdout };
}

function replaceInMarkdown(content, urlMap) {
  const unreplaced = new Set();
  const replaced = content.replace(YUQUE_LINK_RE, match => {
    const normalized = match.replace(/[)>.,;]+$/, '');
    const entry = urlMap[normalized] || urlMap[match];
    if (entry?.lark_url) return entry.lark_url;
    unreplaced.add(match);
    return match;
  });
  return { content: replaced, unreplaced: [...unreplaced] };
}

function main() {
  const args = process.argv.slice(2);
  const book = args.find(a => a.startsWith('--book='))?.split('=')[1];
  const dryRun = args.includes('--dry-run');

  if (!book) {
    console.error('用法: node scripts/migrate/replace-links.mjs --book=知识库名 [--dry-run]');
    process.exit(1);
  }

  const urlMap = readJson(URL_MAP_PATH, {});
  const importState = readJson(statePath(`import-${book}.json`), { imported: {} });
  const cleanRoot = bookCleanDir(book);
  const report = { replaced: [], unreplaced: [], manual_review: [] };

  for (const [yuqueUrl, info] of Object.entries(importState.imported)) {
    if (!info.doc_token) continue;

    const fetch = runLark([
      'docs',
      '+fetch',
      '--as',
      'user',
      '--doc',
      info.doc_token,
      '--format',
      'markdown',
      '--json',
    ]);
    const md =
      fetch.data?.content ||
      fetch.data?.markdown ||
      fetch.data?.data?.content ||
      '';
    if (!md) {
      report.manual_review.push({ title: info.title, reason: 'fetch_failed', yuque_url: yuqueUrl });
      continue;
    }

    const { content, unreplaced } = replaceInMarkdown(md, urlMap);
    if (unreplaced.length > 0) {
      report.unreplaced.push({ title: info.title, links: unreplaced });
    }

    if (content === md) {
      continue;
    }

    if (dryRun) {
      console.log(`[dry-run] 将更新链接: ${info.title}`);
      report.replaced.push({ title: info.title, yuque_url: yuqueUrl });
      continue;
    }

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
      report.replaced.push({ title: info.title, yuque_url: yuqueUrl });
      console.log(`🔗 已替换链接: ${info.title}`);
    } else {
      report.manual_review.push({
        title: info.title,
        reason: 'update_failed',
        error: updated.stderr || updated.stdout,
      });
    }
  }

  writeJson(path.join(cleanRoot, 'link-replace-report.json'), report);
  console.log(`\n✅ 链接替换完成: 更新 ${report.replaced.length} 篇，未替换 ${report.unreplaced.length} 篇`);
}

main();
