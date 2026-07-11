#!/usr/bin/env node
/**
 * 串行导入 Markdown 到飞书 docx，并移入知识库空间
 */
import { spawnSync } from 'child_process';
import fs from 'fs';
import path from 'path';
import {
  appendJsonl,
  bookCleanDir,
  ensureMigrateDirs,
  FAILED_DOCS_PATH,
  readJson,
  statePath,
  URL_MAP_PATH,
  writeJson,
} from './lib/paths.mjs';
import { ROOT } from '../lib/env.mjs';

const WORK_ROOT = ROOT;

function toRelativeFile(absPath) {
  const rel = path.relative(WORK_ROOT, path.resolve(absPath));
  if (rel.startsWith('..') || path.isAbsolute(rel)) {
    throw new Error(`--file 必须是工作目录内的相对路径: ${absPath}`);
  }
  return rel.split(path.sep).join('/');
}

const DANGEROUS_PATH_RE =
  /[\u0000-\u001f\u007f\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]|https?:/i;

function prepareImportFile(fileAbs, doc) {
  const base = path.basename(fileAbs);
  if (!DANGEROUS_PATH_RE.test(base)) {
    return { filePath: toRelativeFile(fileAbs), staged: null };
  }
  const stagingDir = path.join(WORK_ROOT, '_migrate/staging', doc.book_slug || doc.book || 'misc');
  fs.mkdirSync(stagingDir, { recursive: true });
  const slug = doc.slug || `doc-${Date.now()}`;
  const staged = path.join(stagingDir, `${slug}.md`);
  fs.copyFileSync(fileAbs, staged);
  return { filePath: toRelativeFile(staged), staged };
}

function runLark(args, { dryRun = false } = {}) {
  if (dryRun) {
    console.log(`   [dry-run] lark-cli ${args.join(' ')}`);
    return { ok: true, stdout: '{}', data: {} };
  }
  const result = spawnSync('lark-cli', args, { encoding: 'utf8', cwd: WORK_ROOT });
  const stdout = (result.stdout || '').trim();
  const stderr = (result.stderr || '').trim();
  let data = null;
  try {
    data = stdout ? JSON.parse(stdout) : null;
  } catch {
    data = { raw: stdout };
  }
  const ok = result.status === 0 && !data?.error && data?.ok !== false;
  return { ok, status: result.status, stdout, stderr, data };
}

function checkUserAuth() {
  const res = runLark(['auth', 'status', '--json']);
  const user = res.data?.identities?.user;
  if (!user?.available) {
    console.error('❌ 飞书 user 身份未登录。请先执行: lark-cli auth login');
    process.exit(1);
  }
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function ensureFolderNodes(spaceId, docs, folderNodeMap, dryRun) {
  const folders = [...new Set(docs.map(d => d.folder_path).filter(Boolean))].sort(
    (a, b) => a.split('/').length - b.split('/').length,
  );

  for (const folderPath of folders) {
    if (folderNodeMap[folderPath]) continue;
    const parts = folderPath.split('/');
    let parentToken = null;
    let current = '';
    for (const part of parts) {
      current = current ? `${current}/${part}` : part;
      if (folderNodeMap[current]) {
        parentToken = folderNodeMap[current];
        continue;
      }
      const args = [
        'wiki',
        '+node-create',
        '--as',
        'user',
        '--space-id',
        spaceId,
        '--title',
        part,
        '--format',
        'json',
      ];
      if (parentToken) args.push('--parent-node-token', parentToken);
      console.log(`   📁 创建目录节点: ${current}`);
      const res = runLark(args, { dryRun });
      const nodeToken =
        res.data?.node_token ||
        res.data?.data?.node?.node_token ||
        res.data?.data?.node_token;
      if (!res.ok || !nodeToken) {
        console.warn(`   ⚠️  目录节点创建失败: ${current}`, res.stderr || res.stdout);
        folderNodeMap[current] = null;
      } else {
        folderNodeMap[current] = nodeToken;
        parentToken = nodeToken;
      }
    }
  }
  return folderNodeMap;
}

async function importBook(book, { dryRun = false, skipMove = false } = {}) {
  const cleanRoot = bookCleanDir(book);
  const manifestPath = path.join(cleanRoot, 'manifest.json');
  if (!fs.existsSync(manifestPath)) {
    throw new Error(`未找到清洗清单: ${manifestPath}`);
  }
  const manifest = readJson(manifestPath);
  const spaceStatePath = statePath(`space-${book}.json`);
  let spaceState = readJson(spaceStatePath, {});

  if (!spaceState.space_id) {
    console.log(`📚 创建飞书知识空间: ${book}`);
    const createArgs = [
      'wiki',
      '+space-create',
      '--as',
      'user',
      '--name',
      book,
      '--description',
      'Migrated from Yuque',
      '--format',
      'json',
    ];
    const created = runLark(createArgs, { dryRun });
    const spaceId =
      created.data?.space_id ||
      created.data?.data?.space?.space_id ||
      created.data?.data?.space_id;
    if (!spaceId && !dryRun) {
      throw new Error(`创建知识空间失败: ${created.stderr || created.stdout}`);
    }
    spaceState = {
      book,
      space_id: spaceId || 'dry-run-space-id',
      created_at: new Date().toISOString(),
    };
    writeJson(spaceStatePath, spaceState);
    console.log(`   space_id = ${spaceState.space_id}`);
  } else {
    console.log(`📚 使用已有知识空间: ${spaceState.space_id}`);
  }

  const importStatePath = statePath(`import-${book}.json`);
  const importState = readJson(importStatePath, { imported: {}, folder_nodes: {} });
  const urlMap = readJson(URL_MAP_PATH, {});
  const folderNodeMap = { ...importState.folder_nodes };

  ensureFolderNodes(spaceState.space_id, manifest.documents, folderNodeMap, dryRun);
  importState.folder_nodes = folderNodeMap;
  writeJson(importStatePath, importState);

  let success = 0;
  let failed = 0;

  for (const doc of manifest.documents) {
    if (importState.imported[doc.yuque_url]?.doc_token) {
      console.log(`⏭️  已导入，跳过: ${doc.title}`);
      success += 1;
      continue;
    }

    const fileAbs = path.join(cleanRoot, doc.clean_rel_path);
    const { filePath, staged } = prepareImportFile(fileAbs, { ...doc, book });
    console.log(`📄 导入: ${doc.title}${staged ? ' (staging)' : ''}`);
    const importArgs = [
      'drive',
      '+import',
      '--as',
      'user',
      '--type',
      'docx',
      '--file',
      filePath,
      '--name',
      doc.title,
      '--format',
      'json',
    ];
    const imported = runLark(importArgs, { dryRun });
    const docToken =
      imported.data?.token ||
      imported.data?.file_token ||
      imported.data?.data?.result?.token ||
      imported.data?.data?.token;

    if (!imported.ok || !docToken) {
      failed += 1;
      const errEntry = {
        at: new Date().toISOString(),
        book,
        title: doc.title,
        yuque_url: doc.yuque_url,
        file: fileAbs,
        error: imported.stderr || imported.stdout,
      };
      appendJsonl(FAILED_DOCS_PATH, errEntry);
      console.error(`   ❌ 失败: ${doc.title}`);
      await sleep(2000);
      continue;
    }

    let larkUrl =
      imported.data?.url ||
      imported.data?.data?.url ||
      `https://feishu.cn/docx/${docToken}`;

    if (!skipMove) {
      const moveArgs = [
        'wiki',
        '+move',
        '--as',
        'user',
        '--obj-type',
        'docx',
        '--obj-token',
        docToken,
        '--target-space-id',
        spaceState.space_id,
        '--format',
        'json',
      ];
      const parentToken = doc.folder_path ? folderNodeMap[doc.folder_path] : null;
      if (parentToken) moveArgs.push('--target-parent-token', parentToken);

      console.log(`   📦 移入知识库...`);
      const moved = runLark(moveArgs, { dryRun });
      if (!moved.ok) {
        console.warn(`   ⚠️  移入知识库失败，文档已在云空间: ${moved.stderr || moved.stdout}`);
      } else {
        const wikiToken =
          moved.data?.wiki_token ||
          moved.data?.node_token ||
          moved.data?.data?.wiki_token ||
          moved.data?.data?.node_token;
        larkUrl = wikiToken
          ? `https://my.feishu.cn/wiki/${wikiToken}`
          : moved.data?.wiki_url ||
            moved.data?.url ||
            moved.data?.data?.node?.origin_url ||
            moved.data?.data?.url ||
            larkUrl;
      }
    }

    importState.imported[doc.yuque_url] = {
      title: doc.title,
      doc_token: docToken,
      lark_url: larkUrl,
      imported_at: new Date().toISOString(),
      folder_path: doc.folder_path,
    };
    if (doc.yuque_url) {
      urlMap[doc.yuque_url] = {
        lark_url: larkUrl,
        doc_token: docToken,
        title: doc.title,
        book,
      };
    }
    writeJson(importStatePath, importState);
    writeJson(URL_MAP_PATH, urlMap);
    success += 1;
    const done = success + failed;
    console.log(`   ✅ ${larkUrl}  [${done}/${manifest.documents.length}]`);
    await sleep(1500);
  }

  return { book, success, failed, total: manifest.documents.length, space_id: spaceState.space_id };
}

async function main() {
  ensureMigrateDirs();
  const args = process.argv.slice(2);
  const book = args.find(a => a.startsWith('--book='))?.split('=')[1];
  const dryRun = args.includes('--dry-run');
  const skipMove = args.includes('--skip-move');

  if (!book) {
    console.error('用法: node scripts/migrate/import-to-lark.mjs --book=知识库名 [--dry-run]');
    process.exit(1);
  }

  if (!dryRun) checkUserAuth();
  const result = await importBook(book, { dryRun, skipMove });
  console.log(`\n✅ 导入完成: 成功 ${result.success}/${result.total}，失败 ${result.failed}`);
}

main().catch(err => {
  console.error(err);
  process.exit(1);
});
