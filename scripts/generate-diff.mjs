import fs from 'fs';
import path from 'path';
import { pathToFileURL } from 'url';
import { createHash } from 'crypto';
import {
  BACKUP_DIR,
  REPORTS_DIR,
  ensureDirs,
  getYuqueRoot,
  listRepoMirrorDirs,
  loadEnvLocal,
} from './lib/env.mjs';

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

function hashFile(filePath) {
  return createHash('sha256').update(fs.readFileSync(filePath)).digest('hex');
}

function summarizeDiff(before, after) {
  const beforeLines = before.split('\n');
  const afterLines = after.split('\n');
  let added = 0;
  let removed = 0;
  const max = Math.max(beforeLines.length, afterLines.length);
  for (let i = 0; i < max; i += 1) {
    if (beforeLines[i] !== afterLines[i]) {
      if (beforeLines[i] === undefined) added += 1;
      else if (afterLines[i] === undefined) removed += 1;
      else {
        added += 1;
        removed += 1;
      }
    }
  }
  return { added, removed, line_delta: afterLines.length - beforeLines.length };
}

function main() {
  ensureDirs();
  const args = process.argv.slice(2);
  const backupLabel = args.find(a => a.startsWith('--backup='))?.split('=')[1];
  const bookFilter = args.find(a => a.startsWith('--book='))?.split('=')[1];

  const yuqueRoot = getYuqueRoot();

  let backupRoot;
  if (backupLabel) {
    backupRoot = path.join(BACKUP_DIR, backupLabel);
  } else {
    const dirs = fs.existsSync(BACKUP_DIR)
      ? fs
          .readdirSync(BACKUP_DIR)
          .filter(d => fs.statSync(path.join(BACKUP_DIR, d)).isDirectory())
          .map(d => ({
            name: d,
            mtime: fs.statSync(path.join(BACKUP_DIR, d)).mtimeMs,
          }))
          .sort((a, b) => a.mtime - b.mtime)
      : [];
    backupRoot = dirs.length ? path.join(BACKUP_DIR, dirs[dirs.length - 1].name) : null;
  }

  if (!backupRoot || !fs.existsSync(backupRoot)) {
    console.error('❌ 未找到备份目录。请先运行: npm run backup');
    process.exit(1);
  }

  const currentFiles = walkMarkdownRelPaths(yuqueRoot, bookFilter);
  const diffs = [];

  for (const rel of currentFiles) {
    const currentPath = path.join(yuqueRoot, rel);
    const backupPath = path.join(backupRoot, rel);
    if (!fs.existsSync(backupPath)) {
      diffs.push({ rel_path: rel, status: 'added' });
      continue;
    }
    const before = fs.readFileSync(backupPath, 'utf8');
    const after = fs.readFileSync(currentPath, 'utf8');
    if (before !== after) {
      diffs.push({
        rel_path: rel,
        status: 'modified',
        ...summarizeDiff(before, after),
        before_hash: hashFile(backupPath),
        after_hash: hashFile(currentPath),
      });
    }
  }

  const diffDir = path.join(REPORTS_DIR, 'diff');
  fs.mkdirSync(diffDir, { recursive: true });

  const summaryPath = path.join(REPORTS_DIR, 'diff-summary.json');
  fs.writeFileSync(
    summaryPath,
    JSON.stringify(
      {
        generated_at: new Date().toISOString(),
        backup_root: backupRoot,
        yuque_root: yuqueRoot,
        book_filter: bookFilter || null,
        changed_count: diffs.length,
        changes: diffs,
      },
      null,
      2,
    ),
  );

  for (const item of diffs) {
    if (item.status !== 'modified') continue;
    const changelogPath = path.join(diffDir, `${item.rel_path.replace(/\//g, '__')}.changelog.md`);
    fs.mkdirSync(path.dirname(changelogPath), { recursive: true });
    fs.writeFileSync(
      changelogPath,
      [
        `# 变更摘要: ${item.rel_path}`,
        '',
        `- 新增行: ${item.added}`,
        `- 删除行: ${item.removed}`,
        `- 行数变化: ${item.line_delta}`,
        `- 生成时间: ${new Date().toISOString()}`,
        '',
        '## 审核提示',
        '',
        '内容改写类变更请人工确认后再写回语雀。',
      ].join('\n'),
    );
  }

  console.log(`✅ Diff 报告: ${summaryPath}`);
  console.log(`   变更文档: ${diffs.length} 篇`);
}

const isMain =
  process.argv[1] &&
  import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href;

if (isMain) {
  main();
}
