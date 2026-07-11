#!/usr/bin/env node
/**
 * 根据已导入 doc_token 查询 wiki node，刷新 url-map 与 import state 中的 lark_url
 */
import { spawnSync } from 'child_process';
import fs from 'fs';
import path from 'path';
import { CLEAN_DIR, readJson, statePath, URL_MAP_PATH, writeJson } from './lib/paths.mjs';
import { ROOT } from '../lib/env.mjs';

function runLark(args) {
  const result = spawnSync('lark-cli', args, { encoding: 'utf8', cwd: ROOT });
  let data = null;
  try {
    data = result.stdout ? JSON.parse(result.stdout) : null;
  } catch {
    data = null;
  }
  return { ok: result.status === 0 && data?.ok !== false, data };
}

function wikiUrlFromNode(node) {
  if (node?.url) return node.url;
  const token = node?.node_token || node?.wiki_token;
  if (token) return `https://my.feishu.cn/wiki/${token}`;
  return null;
}

function resolveWikiUrl(docToken) {
  const byObj = runLark([
    'wiki',
    'spaces',
    'get_node',
    '--as',
    'user',
    '--params',
    JSON.stringify({ token: docToken, obj_type: 'docx' }),
    '--format',
    'json',
  ]);
  const node = byObj.data?.data?.node || byObj.data?.node;
  if (node) return wikiUrlFromNode(node);

  const byUrl = runLark([
    'wiki',
    '+node-get',
    '--as',
    'user',
    '--node-token',
    `https://my.feishu.cn/docx/${docToken}`,
    '--format',
    'json',
  ]);
  const n2 = byUrl.data?.data;
  return wikiUrlFromNode(n2);
}

function syncBook(book) {
  const importStatePath = statePath(`import-${book}.json`);
  const importState = readJson(importStatePath, { imported: {} });
  const urlMap = readJson(URL_MAP_PATH, {});
  let updated = 0;

  for (const [yuqueUrl, info] of Object.entries(importState.imported)) {
    if (!info.doc_token) continue;
    const wikiUrl = resolveWikiUrl(info.doc_token);
    if (!wikiUrl || wikiUrl === info.lark_url) continue;
    info.lark_url = wikiUrl;
    info.node_token = wikiUrl.split('/').pop();
    if (urlMap[yuqueUrl]) {
      urlMap[yuqueUrl].lark_url = wikiUrl;
      urlMap[yuqueUrl].node_token = info.node_token;
    } else {
      urlMap[yuqueUrl] = {
        lark_url: wikiUrl,
        doc_token: info.doc_token,
        title: info.title,
        book,
        node_token: info.node_token,
      };
    }
    updated += 1;
    console.log(`   ${info.title} → ${wikiUrl}`);
  }

  writeJson(importStatePath, importState);
  writeJson(URL_MAP_PATH, urlMap);
  return updated;
}

function main() {
  const urlMap = readJson(URL_MAP_PATH, {});
  if (!fs.existsSync(CLEAN_DIR)) {
    console.error('未找到 _migrate/clean');
    process.exit(1);
  }

  let total = 0;
  for (const entry of fs.readdirSync(CLEAN_DIR, { withFileTypes: true })) {
    if (!entry.isDirectory()) continue;
    const manifest = path.join(CLEAN_DIR, entry.name, 'manifest.json');
    if (!fs.existsSync(manifest)) continue;
    console.log(`🔗 同步 ${entry.name} wiki URL...`);
    total += syncBook(entry.name);
  }
  console.log(`\n✅ 已更新 ${total} 条 wiki URL`);
}

main();
