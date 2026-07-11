import fs from 'fs';
import path from 'path';
import {
  BACKUP_DIR,
  META_DIR,
  REPORTS_DIR,
  BOOK_SLUG_MAP,
  ensureDirs,
  getRepoConfig,
  getYuqueRoot,
  listRepoMirrorDirs,
  loadEnvLocal,
  resolveDocAbsPath,
} from './lib/env.mjs';
import { getDoc, sleep, updateDoc } from './lib/yuque-api.mjs';
import { assertCloudWriteAllowed, CLOUD_WRITE_WARNING } from './lib/cloud-write.mjs';
import { updatedAtMatches } from './lib/timestamp.mjs';
import {
  checkWebSession,
  closeBrowserContext,
  createDocWeb,
  getDocWeb,
  updateDocWeb,
  useWebPush,
} from './lib/yuque-web-api.mjs';

const YUQUE_CLI = process.env.YUQUE_CLI_PATH || `${process.env.HOME}/.local/bin/yuque`;

const BOOK_SLUG_MAP_LOCAL = BOOK_SLUG_MAP;

function resolveBookSlug(doc, bookFilter) {
  if (doc.book_slug && doc.book_slug !== doc.book && !BOOK_SLUG_MAP_LOCAL[doc.book_slug]) {
    return doc.book_slug;
  }
  const bookName = doc.book || bookFilter;
  return BOOK_SLUG_MAP_LOCAL[bookName] || doc.book_slug || bookName;
}

function loadInventory() {
  const inventoryPath = path.join(META_DIR, 'inventory.json');
  if (!fs.existsSync(inventoryPath)) {
    throw new Error('未找到 inventory.json，请先运行 npm run inventory');
  }
  return JSON.parse(fs.readFileSync(inventoryPath, 'utf8'));
}

function walkMarkdownRelPaths(yuqueRoot, bookFilter) {
  let repos = listRepoMirrorDirs();
  if (bookFilter) {
    repos = repos.filter(r => r.book === bookFilter);
  }
  const results = [];
  for (const { book, mirrorDir } of repos) {
    if (!fs.existsSync(mirrorDir)) continue;
    function walk(dir, base = dir) {
      for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        const full = path.join(dir, entry.name);
        if (entry.name.startsWith('.') || entry.name === '_assets') continue;
        if (entry.isDirectory()) walk(full, base);
        else if (entry.isFile() && entry.name.endsWith('.md')) {
          results.push(`${book}/${path.relative(base, full).replace(/\\/g, '/')}`);
        }
      }
    }
    walk(mirrorDir);
  }
  return results;
}

function diffFromBackup(bookFilter) {
  const backupLabel = `book-${bookFilter.replace(/[^\w\u4e00-\u9fff-]/g, '_')}`;
  const backupRoot = path.join(BACKUP_DIR, backupLabel);
  if (!fs.existsSync(backupRoot)) return null;

  const yuqueRoot = getYuqueRoot();
  const changed = new Set();
  for (const rel of walkMarkdownRelPaths(yuqueRoot, bookFilter)) {
    const currentPath = path.join(yuqueRoot, rel);
    const backupPath = path.join(backupRoot, rel);
    if (!fs.existsSync(backupPath)) {
      changed.add(rel);
      continue;
    }
    if (fs.readFileSync(backupPath, 'utf8') !== fs.readFileSync(currentPath, 'utf8')) {
      changed.add(rel);
    }
  }
  return changed.size ? changed : null;
}

function loadChangedDocs(bookFilter) {
  const summaryPath = path.join(REPORTS_DIR, 'diff-summary.json');
  if (fs.existsSync(summaryPath)) {
    const summary = JSON.parse(fs.readFileSync(summaryPath, 'utf8'));
    if (!bookFilter || summary.book_filter === bookFilter) {
      return new Set(summary.changes.map(c => c.rel_path));
    }
  }
  const fromBackup = bookFilter ? diffFromBackup(bookFilter) : null;
  if (fromBackup) {
    console.log(`📋 从备份 diff 加载 ${fromBackup.size} 篇变更 (book-${bookFilter})`);
    return fromBackup;
  }
  if (fs.existsSync(summaryPath)) {
    return new Set(JSON.parse(fs.readFileSync(summaryPath, 'utf8')).changes.map(c => c.rel_path));
  }
  return null;
}

function stripYuqueFooter(content) {
  const footerMarkers = [
    /\n---\n+\s*>\s*本文档(?:永久)?链接/,
    /\n>\s*作者：/,
    /\n>\s*链接：\s*https:\/\/www\.yuque\.com\//,
  ];
  let result = content;
  for (const marker of footerMarkers) {
    const idx = result.search(marker);
    if (idx !== -1) {
      result = result.slice(0, idx).trimEnd();
    }
  }
  return result;
}

function loadPendingCreates(bookFilter, env) {
  if (!bookFilter) return [];
  const yuqueRoot = getYuqueRoot(env);
  const base = path.join(yuqueRoot, bookFilter);
  const docs = [];
  function walk(dir) {
    if (!fs.existsSync(dir)) return;
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) walk(full);
      else if (entry.name.endsWith('.meta.json')) {
        const meta = JSON.parse(fs.readFileSync(full, 'utf8'));
        if (!meta.slug && meta.rel_path && !meta.rel_path.endsWith('/index.md') && meta.inner_rel_path !== 'index.md') {
          docs.push({
            ...meta,
            slug: null,
            optimizable: true,
            book: meta.book || bookFilter,
            book_slug: meta.book_slug || 'xk57o3',
            group: meta.group || 'hanshihuanyan',
          });
        }
      }
    }
  }
  walk(base);
  return docs;
}

function appendYuqueFooter(content, group, bookSlug, slug) {
  const url = `https://www.yuque.com/${group}/${bookSlug}/${slug}`;
  const stamp = new Date().toISOString().replace('T', ' ').slice(0, 19);
  return `${content.trimEnd()}\n\n> 更新: ${stamp}\n> 原文: <${url}>\n`;
}

async function pushOne({ doc, dryRun, useCli, defaultGroup, env, webPush, force, createNew }) {
  const absPath = resolveDocAbsPath(doc, env);
  const group = doc.group || defaultGroup;
  const bookSlug = resolveBookSlug(doc, doc.book);
  if (!fs.existsSync(absPath)) {
    return { slug: doc.slug, status: 'skipped', reason: '本地文件不存在' };
  }

  const metaPath = absPath.replace(/\.md$/, '.meta.json');
  let slug = doc.slug;
  const title = doc.title || (fs.existsSync(metaPath)
    ? JSON.parse(fs.readFileSync(metaPath, 'utf8')).title
    : path.basename(absPath, '.md'));

  if (!slug) {
    if (!createNew || !webPush) {
      return { slug: null, status: 'skipped', reason: '缺少 slug（用 --create-new 创建）' };
    }
    if (dryRun) {
      return { slug: null, status: 'dry-run', rel_path: doc.rel_path, reason: '将创建新文档' };
    }
    const rawBody = stripYuqueFooter(fs.readFileSync(absPath, 'utf8'));
    const createRes = await createDocWeb(group, bookSlug, {
      title,
      body: rawBody,
      format: 'markdown',
    });
    const created = createRes.data?.data;
    if (!createRes.ok || !created?.slug) {
      return {
        slug: null,
        status: 'failed',
        reason: `创建文档失败 HTTP ${createRes.status}: ${JSON.stringify(createRes.data)?.slice(0, 200)}`,
      };
    }
    slug = created.slug;
    const withFooter = appendYuqueFooter(rawBody, group, bookSlug, slug);
    fs.writeFileSync(absPath, withFooter);
    const meta = fs.existsSync(metaPath)
      ? JSON.parse(fs.readFileSync(metaPath, 'utf8'))
      : {};
    Object.assign(meta, {
      slug,
      group,
      title,
      book: doc.book,
      book_slug: bookSlug,
      rel_path: doc.rel_path,
      remote_updated_at: created.updated_at,
      last_pushed_at: new Date().toISOString(),
    });
    fs.writeFileSync(metaPath, JSON.stringify(meta, null, 2));
    return { slug, status: 'pushed', rel_path: doc.rel_path, reason: '已创建' };
  }

  if (dryRun) {
    return { slug, status: 'dry-run', rel_path: doc.rel_path };
  }

  const body = stripYuqueFooter(fs.readFileSync(absPath, 'utf8'));

  let remoteDoc;
  let remoteUpdatedAt;

  if (webPush) {
    const remote = await getDocWeb(group, bookSlug, slug, { edit: true });
    if (!remote.ok) {
      return {
        slug: doc.slug,
        status: 'failed',
        reason: `获取远程文档失败 HTTP ${remote.status}`,
      };
    }
    remoteDoc = remote.data;
    remoteUpdatedAt = remoteDoc?.updated_at;

    const remoteFormat = remoteDoc?.format || 'lake';
    if (remoteFormat === 'lake' || remoteFormat === 'html') {
      return {
        slug: doc.slug,
        status: 'skipped',
        reason: `云端为 ${remoteFormat} 格式，禁止 API 写回（请在语雀网页端编辑）`,
      };
    }
  } else {
    const remote = await getDoc(group, bookSlug, slug);
    if (!remote.ok) {
      return {
        slug: doc.slug,
        status: 'failed',
        reason: `获取远程文档失败 HTTP ${remote.status}`,
      };
    }
    remoteDoc = remote.data?.data;
    remoteUpdatedAt = remoteDoc?.updated_at;
  }

  if (fs.existsSync(metaPath) && !force) {
    const meta = JSON.parse(fs.readFileSync(metaPath, 'utf8'));
    const timestampMismatch =
      meta.remote_updated_at &&
      remoteUpdatedAt &&
      !updatedAtMatches(meta.remote_updated_at, remoteUpdatedAt);
    if (timestampMismatch) {
      const remoteBody = stripYuqueFooter(
        remoteDoc.body || remoteDoc.content || remoteDoc.sourcecode || '',
      );
      if (remoteBody.trim() === body.trim()) {
        meta.remote_updated_at = remoteUpdatedAt;
        meta.last_reconciled_at = new Date().toISOString();
        fs.writeFileSync(metaPath, JSON.stringify(meta, null, 2));
        return {
          slug: doc.slug,
          status: 'synced-meta',
          rel_path: doc.rel_path,
          reason: '内容与云端一致，已刷新时间戳',
        };
      }
      return {
        slug: doc.slug,
        status: 'conflict',
        reason: '云端已被他人修改，跳过写回（可用 --force 强制覆盖）',
        remote_updated_at: remoteUpdatedAt,
        local_snapshot: meta.remote_updated_at,
      };
    }
  }

  let pushedUpdatedAt = remoteUpdatedAt;

  if (useCli && fs.existsSync(YUQUE_CLI)) {
    const { spawnSync } = await import('child_process');
    const target = `${group}/${bookSlug}/${slug}`;
    const pushResult = spawnSync(
      YUQUE_CLI,
      ['doc', 'update', target, '-F', absPath],
      { encoding: 'utf8' },
    );
    if (pushResult.status !== 0) {
      return {
        slug: doc.slug,
        status: 'failed',
        reason: pushResult.stderr || pushResult.stdout || 'yuque-cli 失败',
      };
    }
  } else if (webPush) {
    const remoteFormat = remoteDoc?.format || 'markdown';
    const res = await updateDocWeb(remoteDoc.id, {
      body,
      title: title || remoteDoc.title,
      format: remoteFormat === 'markdown' ? 'markdown' : remoteFormat,
    });
    if (!res.ok) {
      return {
        slug: doc.slug,
        status: 'failed',
        reason: `写回失败 HTTP ${res.status}: ${JSON.stringify(res.data)?.slice(0, 200)}`,
      };
    }
    const refreshed = await getDocWeb(group, bookSlug, slug);
    pushedUpdatedAt = refreshed.data?.updated_at || remoteUpdatedAt;
  } else {
    const res = await updateDoc(group, bookSlug, slug, body);
    if (!res.ok) {
      return {
        slug: doc.slug,
        status: 'failed',
        reason: `写回失败 HTTP ${res.status}: ${JSON.stringify(res.data)?.slice(0, 200)}`,
      };
    }
  }

  if (fs.existsSync(metaPath)) {
    const meta = JSON.parse(fs.readFileSync(metaPath, 'utf8'));
    meta.remote_updated_at = pushedUpdatedAt;
    meta.last_pushed_at = new Date().toISOString();
    fs.writeFileSync(metaPath, JSON.stringify(meta, null, 2));
  }

  return { slug, status: 'pushed', rel_path: doc.rel_path };
}

async function main() {
  ensureDirs();
  const args = process.argv.slice(2);
  const dryRun = args.includes('--dry-run');
  const useCli = args.includes('--use-cli');
  const force = args.includes('--force');
  const createNew = args.includes('--create-new');
  const pushAll = args.includes('--all');
  const folderFilter = args.find(a => a.startsWith('--folder='))?.split('=')[1];
  const bookFilter = args.find(a => a.startsWith('--book='))?.split('=')[1];

  const env = loadEnvLocal();
  if (!dryRun) {
    assertCloudWriteAllowed(env);
    console.warn(`⚠️  ${CLOUD_WRITE_WARNING}`);
  }
  const { group: defaultGroup } = getRepoConfig(env);
  const { documents } = loadInventory();
  const changedSet = pushAll ? null : loadChangedDocs(bookFilter);

  let targets = documents.filter(d => d.optimizable && d.slug);
  if (bookFilter) {
    targets = targets.filter(d => d.book === bookFilter);
  }
  if (folderFilter) {
    targets = targets.filter(
      d =>
        d.folder_path === folderFilter ||
        d.folder_path === folderFilter.replace(/^\//, ''),
    );
  }
  if (changedSet) {
    targets = targets.filter(d => changedSet.has(d.rel_path));
  }

  function enrichFromMeta(doc) {
    const absPath = resolveDocAbsPath(doc, env);
    const metaPath = absPath.replace(/\.md$/, '.meta.json');
    if (!fs.existsSync(metaPath)) return doc;
    const meta = JSON.parse(fs.readFileSync(metaPath, 'utf8'));
    return {
      ...doc,
      slug: doc.slug || meta.slug || null,
      book_slug: resolveBookSlug(
        { ...doc, book_slug: meta.book_slug ?? doc.book_slug },
        doc.book,
      ),
      title: doc.title || meta.title,
    };
  }
  targets = targets.map(enrichFromMeta);

  if (createNew && bookFilter) {
    const pending = loadPendingCreates(bookFilter, env);
    const existing = new Set(targets.map(d => d.rel_path));
    for (const p of pending) {
      if (!existing.has(p.rel_path)) targets.push(p);
    }
  }

  const webPush = useWebPush(env);
  if (webPush && !dryRun) {
    const session = await checkWebSession();
    if (!session.ok) {
      throw new Error(
        `浏览器登录态无效 (HTTP ${session.status})，请运行 npm run get-token 或 npm run export-cookie`,
      );
    }
    console.log(`🔐 写回模式: 浏览器 Web API (用户 ${session.login})`);
  } else if (!dryRun) {
    console.log('🔐 写回模式: v2 API (Personal Token)');
  }

  console.log(`📤 写回目标: ${targets.length} 篇 (${dryRun ? 'dry-run' : 'live'})`);

  const results = [];
  try {
  for (const doc of targets) {
    const result = await pushOne({ doc, dryRun, useCli, defaultGroup, env, webPush, force, createNew });
    results.push(result);
    const icon =
      result.status === 'pushed' || result.status === 'dry-run' || result.status === 'synced-meta'
        ? '✅'
        : result.status === 'conflict'
          ? '⚠️'
          : result.status === 'skipped'
            ? '⏭️'
            : '❌';
    console.log(
      `${icon} ${doc.rel_path} — ${result.status}${result.reason ? `: ${result.reason}` : ''}`,
    );
    if (!dryRun) {
      await sleep(220);
    }
  }
  } finally {
    if (webPush) await closeBrowserContext();
  }

  const logPath = path.join(META_DIR, 'push-log.json');
  const prev = fs.existsSync(logPath)
    ? JSON.parse(fs.readFileSync(logPath, 'utf8'))
    : { runs: [] };
  prev.runs.push({
    at: new Date().toISOString(),
    dry_run: dryRun,
    folder_filter: folderFilter || null,
    total: targets.length,
    pushed: results.filter(r => r.status === 'pushed').length,
    synced_meta: results.filter(r => r.status === 'synced-meta').length,
    failed: results.filter(r => r.status === 'failed').length,
    conflicts: results.filter(r => r.status === 'conflict').length,
    results,
  });
  fs.writeFileSync(logPath, JSON.stringify(prev, null, 2));

  const failed = results.filter(r => r.status === 'failed').length;
  if (failed > 0) process.exit(1);
}

main().catch(err => {
  console.error(`❌ ${err.message}`);
  process.exit(1);
});
