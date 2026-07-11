#!/usr/bin/env node
/**
 * 使用语雀个人 Token (X-Auth-Token) 同步知识库
 * npm run sync-all  # 有 YUQUE_PERSONAL_TOKEN 时自动走此路径
 */
import fs from 'fs';
import path from 'path';
import {
  META_DIR,
  ensureDirs,
  getRepoConfig,
  getYuqueRoot,
  loadEnvLocal,
  slugToBookFolder,
} from './lib/env.mjs';
import {
  getCurrentUser,
  getDocById,
  getRepoToc,
  listUserRepos,
  sleep,
} from './lib/yuque-api.mjs';

function sanitizeFilename(name) {
  return name.replace(/[\\/:*?"<>|]/g, '_').trim() || 'untitled';
}

function buildTocMaps(toc) {
  const byUuid = new Map();
  for (const item of toc) {
    byUuid.set(item.uuid, item);
  }

  function folderPath(uuid) {
    const item = byUuid.get(uuid);
    if (!item) return [];
    const parent = item.parent_uuid ? folderPath(item.parent_uuid) : [];
    if (item.type === 'TITLE') {
      return [...parent, sanitizeFilename(item.title)];
    }
    return parent;
  }

  return { byUuid, folderPath };
}

function appendDocFooter(body, doc, repo) {
  const link = doc.url || `https://www.yuque.com/${repo.namespace}/${doc.slug}`;
  return `${body.trimEnd()}\n\n---\n> 本文档永久链接：${link}\n`;
}

function writeMetaSidecar(absPath, meta) {
  const metaPath = absPath.replace(/\.md$/, '.meta.json');
  const existing = fs.existsSync(metaPath)
    ? JSON.parse(fs.readFileSync(metaPath, 'utf8'))
    : {};
  const merged = {
    ...existing,
    ...meta,
    remote_updated_at: meta.remote_updated_at ?? existing.remote_updated_at,
    last_synced_at: new Date().toISOString(),
  };
  fs.writeFileSync(metaPath, JSON.stringify(merged, null, 2));
}

async function downloadDoc({ bookId, docNode, folderParts, mirrorDir, repo, bookFolder }) {
  if (docNode.type !== 'DOC') return null;

  const docId = docNode.doc_id || docNode.id;
  const res = await getDocById(bookId, docId);
  if (!res.ok) {
    console.warn(`   ⚠️  跳过 ${docNode.title}: HTTP ${res.status}`);
    return null;
  }

  const doc = res.data?.data;
  if (!doc?.slug) return null;

  const format = doc.format || doc.content_type;
  if (format && format !== 'markdown' && format !== 'md') {
    console.warn(`   ⏭️  跳过非 Markdown: ${docNode.title} (${format})`);
    return null;
  }

  const body = doc.body || doc.content || '';
  const relDir = path.join(mirrorDir, ...folderParts);
  fs.mkdirSync(relDir, { recursive: true });

  const filename = `${sanitizeFilename(doc.title || docNode.title)}.md`;
  const absPath = path.join(relDir, filename);
  fs.writeFileSync(absPath, appendDocFooter(body, doc, repo));

  const innerRel = path.relative(mirrorDir, absPath).replace(/\\/g, '/');
  writeMetaSidecar(absPath, {
    slug: doc.slug,
    group: repo.namespace?.split('/')[0] || repo.user?.login,
    title: doc.title || docNode.title,
    book: bookFolder || repo.slug,
    book_slug: repo.slug,
    rel_path: `${bookFolder || repo.slug}/${innerRel}`,
    inner_rel_path: innerRel,
    folder_path: folderParts.join('/'),
    remote_updated_at: doc.updated_at,
  });

  return innerRel;
}

async function syncOneRepo(repo, yuqueRoot, env, bookFolder) {
  const bookSlug = repo.slug;
  const mirrorDir = path.join(yuqueRoot, bookFolder || bookSlug);
  fs.mkdirSync(mirrorDir, { recursive: true });

  console.log(`\n📚 ${repo.name} (${repo.namespace}) → ${mirrorDir}`);

  const toc = await getRepoToc(repo.id, env);
  const { byUuid, folderPath } = buildTocMaps(toc);
  const docNodes = toc.filter(item => item.type === 'DOC');
  let count = 0;

  for (const node of docNodes) {
    const parts = node.parent_uuid ? folderPath(node.parent_uuid) : [];
    const rel = await downloadDoc({
      bookId: repo.id,
      docNode: node,
      folderParts: parts,
      mirrorDir,
      repo,
      bookFolder,
    });
    if (rel) {
      count += 1;
      console.log(`   ✅ ${rel}`);
    }
    await sleep(120);
  }

  // 无 toc 文档时的兜底：直接拉文档列表
  if (docNodes.length === 0) {
    console.log('   ℹ️  目录为空，跳过');
  }

  return { book: bookSlug, count, mirrorDir };
}

function appendSyncLog(entry) {
  const syncLogPath = path.join(META_DIR, 'sync-log.json');
  const prev = fs.existsSync(syncLogPath)
    ? JSON.parse(fs.readFileSync(syncLogPath, 'utf8'))
    : { runs: [] };
  prev.runs.push(entry);
  prev.lastSync = new Date().toISOString();
  fs.writeFileSync(syncLogPath, JSON.stringify(prev, null, 2));
}

async function main() {
  ensureDirs();
  const args = process.argv.slice(2);
  const syncAll = args.includes('--all');
  const env = loadEnvLocal();
  const yuqueRoot = getYuqueRoot(env);

  const userRes = await getCurrentUser(env);
  if (!userRes.ok) {
    console.error(`❌ 认证失败 HTTP ${userRes.status}，请检查 YUQUE_PERSONAL_TOKEN`);
    process.exit(1);
  }

  const login = userRes.data?.data?.login;
  console.log(`👤 用户: ${login}`);

  let repos;
  if (syncAll) {
    repos = await listUserRepos(login, env);
    console.log(`📥 同步全部知识库 (${repos.length} 个) → ${yuqueRoot}`);
  } else {
    const { repoUrl, book } = getRepoConfig(env);
    const all = await listUserRepos(login, env);
    const found = all.find(r => r.slug === book);
    if (!found) {
      console.error(`❌ 未找到知识库: ${repoUrl}`);
      process.exit(1);
    }
    repos = [found];
    console.log(`📥 同步知识库: ${repoUrl}`);
  }

  const results = [];
  for (const repo of repos) {
    const bookFolder = slugToBookFolder(repo.slug, env);
    const result = await syncOneRepo(repo, yuqueRoot, env, bookFolder);
    results.push(result);
  }

  appendSyncLog({
    at: new Date().toISOString(),
    mode: syncAll ? 'api-all' : 'api-single',
    yuqueRoot,
    repos: results,
    total_docs: results.reduce((n, r) => n + r.count, 0),
  });

  console.log(`\n✅ API 同步完成，共 ${results.reduce((n, r) => n + r.count, 0)} 篇`);
  console.log('   运行 npm run inventory && npm run reconcile-meta 更新清单与时间戳');
}

main().catch(err => {
  console.error(`❌ ${err.message}`);
  process.exit(1);
});
