#!/usr/bin/env node
/**
 * 修复被 API 写回破坏的 Lake 文档（正文中混入 Markdown）。
 *
 * npm run restore-cloud -- --fix-corrupted --dry-run
 * npm run restore-cloud -- --fix-corrupted --book=金融
 */
import fs from 'fs';
import path from 'path';
import {
  META_DIR,
  REPORTS_DIR,
  ensureDirs,
  getRepoConfig,
  loadEnvLocal,
  resolveDocAbsPath,
} from './lib/env.mjs';
import { sleep } from './lib/yuque-api.mjs';
import {
  checkWebSession,
  closeBrowserContext,
  getDocWeb,
  getDocVersionWeb,
  listDocVersionsWeb,
  updateDocWeb,
  useWebPush,
} from './lib/yuque-web-api.mjs';

function loadInventory() {
  return JSON.parse(fs.readFileSync(path.join(META_DIR, 'inventory.json'), 'utf8'));
}

function isCorruptedLakeDoc(doc) {
  const format = doc.format || 'lake';
  const body = doc.body || '';
  if (format !== 'lake') return format === 'markdown';
  const isMd = body.trim().startsWith('#');
  const hasLakeHtml = body.includes('lake-content');
  const aslLen = (doc.body_asl || '').length;
  return isMd && !hasLakeHtml && aslLen < 100;
}

function scoreVersion(version) {
  const body = version.body || '';
  const asl = version.body_asl || '';
  let score = 0;
  if (body.includes('lake-content')) score += 100;
  if (asl.length > 100) score += 80;
  if (body.length > 200 && !body.trim().startsWith('#')) score += 40;
  score += Math.min(body.length, 5000) / 100;
  score += Math.min(asl.length, 5000) / 100;
  return score;
}

async function pickBestVersion(versions) {
  let best = null;
  let bestScore = -1;
  for (const v of versions) {
    const detail = await getDocVersionWeb(v.id);
    if (!detail.ok || !detail.data) continue;
    const score = scoreVersion(detail.data);
    if (score > bestScore) {
      bestScore = score;
      best = { version: v, detail: detail.data, score };
    }
  }
  return bestScore > 0 ? best : null;
}

function buildRestorePayload(version) {
  const payload = {
    title: version.title,
    format: 'lake',
  };
  if (version.body_asl) payload.body_asl = version.body_asl;
  if (version.body) payload.body = version.body;
  if (version.body_html) payload.body_html = version.body_html;
  return payload;
}

async function restoreOne(doc, { dryRun, defaultGroup, fixCorrupted }) {
  const group = doc.group || defaultGroup;
  const bookSlug = doc.book_slug || doc.book;

  const remote = await getDocWeb(group, bookSlug, doc.slug, { edit: true });
  if (!remote.ok || !remote.data?.id) {
    return { rel_path: doc.rel_path, status: 'failed', reason: `无法获取文档 HTTP ${remote.status}` };
  }

  const current = remote.data;
  if (fixCorrupted && !isCorruptedLakeDoc(current)) {
    return { rel_path: doc.rel_path, status: 'skipped', reason: '文档格式正常，无需修复' };
  }

  const docId = current.id;

  // 优先用编辑器草稿中的 body_draft_asl 恢复 Lake 格式
  if (fixCorrupted && isCorruptedLakeDoc(current) && current.body_draft_asl?.length > 50) {
    const payload = {
      title: current.title,
      format: 'lake',
      body_asl: current.body_draft_asl,
    };
    if (dryRun) {
      return {
        rel_path: doc.rel_path,
        status: 'dry-run',
        reason: `将用 body_draft_asl (${current.body_draft_asl.length} 字节) 恢复 Lake 格式`,
      };
    }
    const res = await updateDocWeb(docId, payload);
    if (res.ok) {
      return { rel_path: doc.rel_path, status: 'restored', reason: '已从 body_draft_asl 恢复 Lake 格式' };
    }
  }

  const versionsRes = await listDocVersionsWeb(docId, 100);
  if (!versionsRes.ok) {
    return { rel_path: doc.rel_path, status: 'failed', reason: '无法读取历史版本' };
  }

  const picked = await pickBestVersion(versionsRes.data);
  if (!picked) {
    return {
      rel_path: doc.rel_path,
      status: 'skipped',
      reason: '历史版本中无可用 Lake 正文，请在语雀网页端手动恢复历史版本',
    };
  }

  const payload = buildRestorePayload(picked.detail);
  if (!payload.body_asl && !payload.body?.includes('lake-content')) {
    return {
      rel_path: doc.rel_path,
      status: 'skipped',
      reason: '最佳历史版本仍为 Markdown，请手动在语雀恢复',
    };
  }

  if (dryRun) {
    return {
      rel_path: doc.rel_path,
      status: 'dry-run',
      reason: `将恢复到 ${picked.version.created_at} (score ${picked.score.toFixed(1)})`,
    };
  }

  const res = await updateDocWeb(docId, payload);
  if (!res.ok) {
    return {
      rel_path: doc.rel_path,
      status: 'failed',
      reason: `恢复失败 HTTP ${res.status}: ${JSON.stringify(res.data)?.slice(0, 120)}`,
    };
  }

  return {
    rel_path: doc.rel_path,
    status: 'restored',
    reason: `已恢复到 ${picked.version.created_at}`,
  };
}

async function main() {
  ensureDirs();
  const args = process.argv.slice(2);
  const dryRun = args.includes('--dry-run');
  const bookFilter = args.find(a => a.startsWith('--book='))?.split('=')[1];
  const fixCorrupted = args.includes('--fix-corrupted') || !args.includes('--before');
  const onlyPushed = !args.includes('--all-docs');

  const env = loadEnvLocal();
  if (!useWebPush(env)) {
    throw new Error('恢复需浏览器 Cookie 登录，请运行 npm run get-token');
  }

  const session = await checkWebSession();
  if (!session.ok) {
    throw new Error('浏览器登录态无效，请运行 npm run get-token');
  }

  const { group: defaultGroup } = getRepoConfig(env);
  const { documents } = loadInventory();
  let targets = documents.filter(d => d.slug);

  if (bookFilter) {
    targets = targets.filter(d => d.book === bookFilter);
  }

  if (onlyPushed) {
    targets = targets.filter(d => {
      const metaPath = resolveDocAbsPath(d, env).replace(/\.md$/, '.meta.json');
      if (!fs.existsSync(metaPath)) return false;
      const meta = JSON.parse(fs.readFileSync(metaPath, 'utf8'));
      return meta.last_pushed_at && meta.last_pushed_at >= '2026-07-05T00:00:00';
    });
  }

  if (fixCorrupted) {
    const reportPath = path.join(REPORTS_DIR, 'corrupted-docs.json');
    if (fs.existsSync(reportPath) && !bookFilter) {
      const report = JSON.parse(fs.readFileSync(reportPath, 'utf8'));
      const set = new Set(report.corrupted || []);
      targets = targets.filter(d => set.has(d.rel_path));
      console.log(`   使用扫描报告: ${report.corrupted_count} 篇损坏`);
    }
  }

  console.log(`🔄 修复云端 Lake 文档 (${dryRun ? 'dry-run' : 'live'})`);
  console.log(`   用户: ${session.login}`);
  console.log(`   模式: ${fixCorrupted ? '仅修复损坏文档' : '按时间恢复'}`);
  console.log(`   候选: ${targets.length} 篇`);

  const results = [];
  try {
    for (const doc of targets) {
      const result = await restoreOne(doc, { dryRun, defaultGroup, fixCorrupted });
      results.push(result);
      if (result.status !== 'skipped' || !fixCorrupted) {
        const icon =
          result.status === 'restored' || result.status === 'dry-run'
            ? '✅'
            : result.status === 'skipped'
              ? '⏭️'
              : '❌';
        console.log(`${icon} ${result.rel_path} — ${result.status}${result.reason ? `: ${result.reason}` : ''}`);
      }
      await sleep(300);
    }
  } finally {
    await closeBrowserContext();
  }

  const restored = results.filter(r => r.status === 'restored').length;
  const skipped = results.filter(r => r.status === 'skipped').length;
  const failed = results.filter(r => r.status === 'failed').length;
  const needFix = results.filter(r => r.status === 'dry-run' || r.status === 'restored' || (r.reason && r.reason.includes('手动'))).length;
  console.log(`\n✅ 完成: 恢复 ${restored}，跳过 ${skipped}，失败 ${failed}`);
  if (fixCorrupted && skipped > 0) {
    console.log('   无法自动修复的文档：在语雀网页打开 → 右上角「历史」→「恢复此版本」');
  }
  if (failed > 0) process.exit(1);
}

main().catch(err => {
  console.error(`❌ ${err.message}`);
  process.exit(1);
});
