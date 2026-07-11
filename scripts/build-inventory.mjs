import fs from 'fs';
import path from 'path';
import {
  META_DIR,
  REPORTS_DIR,
  BOOK_SLUG_MAP,
  ensureDirs,
  getRepoConfig,
  listRepoMirrorDirs,
  getYuqueRoot,
  loadEnvLocal,
} from './lib/env.mjs';

const SLUG_URL_RE =
  /https?:\/\/(?:www\.)?yuque\.com\/([^/\s]+)\/([^/\s]+)\/([a-zA-Z0-9_-]+)/;

const BOOK_SLUG_MAP_LOCAL = BOOK_SLUG_MAP;

function readMetaSidecar(absPath) {
  const metaPath = absPath.replace(/\.md$/, '.meta.json');
  if (!fs.existsSync(metaPath)) return null;
  try {
    return JSON.parse(fs.readFileSync(metaPath, 'utf8'));
  } catch {
    return null;
  }
}

function walkMarkdownFiles(dir, base = dir) {
  const results = [];
  if (!fs.existsSync(dir)) return results;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.name.startsWith('.') || entry.name === '_assets') continue;
    if (entry.isDirectory()) {
      results.push(...walkMarkdownFiles(full, base));
    } else if (entry.isFile() && entry.name.endsWith('.md')) {
      results.push({
        absPath: full,
        relPath: path.relative(base, full),
        folderPath: path.dirname(path.relative(base, full)),
      });
    }
  }
  return results;
}

function extractDocMeta(content, fallbackBook, fallbackGroup) {
  const matches = [...content.matchAll(new RegExp(SLUG_URL_RE.source, 'g'))];
  if (matches.length === 0) {
    return { slug: null, group: fallbackGroup, book: fallbackBook };
  }
  const last = matches[matches.length - 1];
  return {
    group: last[1],
    book: last[2],
    slug: last[3],
  };
}

function extractTitle(content, filename) {
  const h1 = content.match(/^#\s+(.+)$/m);
  if (h1) return h1[1].trim();
  return path.basename(filename, '.md');
}

function countWords(text) {
  const stripped = text
    .replace(/```[\s\S]*?```/g, '')
    .replace(/!\[[^\]]*\]\([^)]+\)/g, '')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/[#>*_\-\|`]/g, ' ')
    .trim();
  const cjk = (stripped.match(/[\u4e00-\u9fff]/g) || []).length;
  const latin = (stripped.match(/[a-zA-Z0-9]+/g) || []).length;
  return cjk + latin;
}

function hasHeadingLevels(content) {
  return /^#{2,6}\s+/m.test(content);
}

function detectSkipReason(relPath, content) {
  const lower = relPath.toLowerCase();
  if (lower.includes('画板') || lower.includes('board')) {
    return '画板文档，需手动处理';
  }
  if (lower.endsWith('.sheet.md') || lower.includes('数据表')) {
    return '表格/数据表类型，API 写回可能不兼容';
  }
  if (content.trim().length === 0) {
    return '空文档';
  }
  return null;
}

function writeMetaSidecar(absPath, meta) {
  const metaPath = absPath.replace(/\.md$/, '.meta.json');
  fs.writeFileSync(metaPath, JSON.stringify(meta, null, 2));
}

function buildScanReport(inventory, yuqueRoot) {
  const folders = new Set(inventory.map(d => d.folder_path).filter(Boolean));
  const empty = inventory.filter(d => d.word_count === 0);
  const noHeadings = inventory.filter(d => !d.has_heading_levels && d.word_count > 100);
  const noSlug = inventory.filter(d => !d.slug);
  const skipped = inventory.filter(d => d.skip_reason);
  const titleMap = {};
  for (const doc of inventory) {
    titleMap[doc.title] = titleMap[doc.title] || [];
    titleMap[doc.title].push(doc.rel_path);
  }
  const duplicateTitles = Object.entries(titleMap).filter(([, paths]) => paths.length > 1);

  const lines = [
    '# 语雀知识库结构扫描报告',
    '',
    `生成时间: ${new Date().toISOString()}`,
    `数据目录: \`${yuqueRoot}\``,
    '',
    '## 概览',
    '',
    `| 指标 | 数量 |`,
    `|------|------|`,
    `| 文档总数 | ${inventory.length} |`,
    `| 文件夹数 | ${folders.size} |`,
    `| 需跳过 | ${skipped.length} |`,
    `| 空文档 | ${empty.length} |`,
    `| 无 slug | ${noSlug.length} |`,
    `| 重复标题 | ${duplicateTitles.length} |`,
    '',
  ];

  if (skipped.length) {
    lines.push('## 需跳过的文档', '');
    for (const doc of skipped) {
      lines.push(`- \`${doc.rel_path}\` — ${doc.skip_reason}`);
    }
    lines.push('');
  }

  if (empty.length) {
    lines.push('## 空文档', '');
    for (const doc of empty) {
      lines.push(`- \`${doc.rel_path}\``);
    }
    lines.push('');
  }

  if (noHeadings.length) {
    lines.push('## 无二级以上标题（>100字）', '');
    for (const doc of noHeadings.slice(0, 30)) {
      lines.push(`- \`${doc.rel_path}\` (${doc.word_count} 字)`);
    }
    if (noHeadings.length > 30) {
      lines.push(`- ... 另有 ${noHeadings.length - 30} 篇`);
    }
    lines.push('');
  }

  if (duplicateTitles.length) {
    lines.push('## 重复标题', '');
    for (const [title, paths] of duplicateTitles) {
      lines.push(`### ${title}`, '');
      for (const p of paths) {
        lines.push(`- \`${p}\``);
      }
      lines.push('');
    }
  }

  if (noSlug.length) {
    lines.push('## 无法提取 slug 的文档', '');
    lines.push('写回前需手动补充 slug 或重新同步。', '');
    for (const doc of noSlug.slice(0, 20)) {
      lines.push(`- \`${doc.rel_path}\``);
    }
    lines.push('');
  }

  return lines.join('\n');
}

function scanRepoMirror({ book, mirrorDir, defaultGroup }) {
  const files = walkMarkdownFiles(mirrorDir);
  const inventory = [];

  for (const file of files) {
    const content = fs.readFileSync(file.absPath, 'utf8');
    const existingMeta = readMetaSidecar(file.absPath);
    const { slug: urlSlug, group: urlGroup, book: urlBook } = extractDocMeta(
      content,
      book,
      defaultGroup,
    );
    const slug = urlSlug || existingMeta?.slug || null;
    const group = urlGroup || existingMeta?.group || defaultGroup;
    const bookSlug =
      urlBook ||
      existingMeta?.book_slug ||
      BOOK_SLUG_MAP_LOCAL[book] ||
      book;
    const title = extractTitle(content, file.relPath);
    const skipReason = detectSkipReason(file.relPath, content);
    const innerRel = file.relPath.replace(/\\/g, '/');
    const relPath = `${book}/${innerRel}`;

    const item = {
      slug,
      group,
      title,
      rel_path: relPath,
      inner_rel_path: innerRel,
      folder_path: file.folderPath === '.' ? '' : file.folderPath.replace(/\\/g, '/'),
      word_count: countWords(content),
      has_images: /!\[[^\]]*\]\([^)]+\)/.test(content),
      has_heading_levels: hasHeadingLevels(content),
      optimizable: !skipReason && !!slug,
      skip_reason: skipReason,
      book,
      book_slug: bookSlug,
      mirror_dir: mirrorDir,
    };
    inventory.push(item);
    writeMetaSidecar(file.absPath, {
      slug,
      group,
      title,
      book,
      book_slug: bookSlug,
      rel_path: relPath,
      inner_rel_path: innerRel,
      folder_path: item.folder_path,
      ...(existingMeta?.remote_updated_at
        ? { remote_updated_at: existingMeta.remote_updated_at }
        : {}),
      ...(existingMeta?.last_pushed_at
        ? { last_pushed_at: existingMeta.last_pushed_at }
        : {}),
    });
  }

  return inventory;
}

function main() {
  ensureDirs();
  const env = loadEnvLocal();
  const yuqueRoot = getYuqueRoot(env);
  const { group: defaultGroup } = getRepoConfig(env);
  const repos = listRepoMirrorDirs(env);

  if (repos.length === 0) {
    console.error(
      `❌ 未找到知识库镜像。请先运行:\n   npm run sync-all\n   或 npm run sync`,
    );
    process.exit(1);
  }

  let inventory = [];
  for (const repo of repos) {
    inventory = inventory.concat(scanRepoMirror({ ...repo, defaultGroup }));
  }

  inventory.sort((a, b) => a.rel_path.localeCompare(b.rel_path, 'zh-CN'));

  const inventoryPath = path.join(META_DIR, 'inventory.json');
  fs.writeFileSync(
    inventoryPath,
    JSON.stringify(
      {
        generated_at: new Date().toISOString(),
        yuque_root: yuqueRoot,
        repos: repos.map(r => r.book),
        total: inventory.length,
        documents: inventory,
      },
      null,
      2,
    ),
  );

  const reportPath = path.join(REPORTS_DIR, 'scan-issues.md');
  fs.writeFileSync(reportPath, buildScanReport(inventory, yuqueRoot));

  console.log(`✅ 清单已写入 ${inventoryPath}`);
  console.log(`✅ 扫描报告已写入 ${reportPath}`);
  console.log(`   文档: ${inventory.length}，可优化: ${inventory.filter(d => d.optimizable).length}`);
}

main();
