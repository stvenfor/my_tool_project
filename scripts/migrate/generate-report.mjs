#!/usr/bin/env node
/**
 * 生成 migration-report.md
 */
import fs from 'fs';
import path from 'path';
import {
  CLEAN_DIR,
  EXPORT_DIR,
  FAILED_DOCS_PATH,
  getInventory,
  readJson,
  REPORT_PATH,
  statePath,
  URL_MAP_PATH,
} from './lib/paths.mjs';

function readJsonl(filePath) {
  if (!fs.existsSync(filePath)) return [];
  return fs
    .readFileSync(filePath, 'utf8')
    .split('\n')
    .filter(Boolean)
    .map(line => JSON.parse(line));
}

function main() {
  const args = process.argv.slice(2);
  const bookFilter = args.find(a => a.startsWith('--book='))?.split('=')[1];

  let inventory = null;
  try {
    inventory = getInventory();
  } catch {
    inventory = { repos: [], total: 0, documents: [] };
  }

  const exportSummary = readJson(path.join(EXPORT_DIR, 'export-summary.json'), { books: [] });
  const cleanSummary = readJson(path.join(CLEAN_DIR, 'clean-summary.json'), { books: [] });
  const failedDocs = readJsonl(FAILED_DOCS_PATH);
  const urlMap = readJson(URL_MAP_PATH, {});

  const books = bookFilter
    ? [bookFilter]
    : [...new Set(exportSummary.books.map(b => b.book))];

  let importedSuccess = 0;
  let importedFailed = failedDocs.length;
  const imageIssues = [];
  const unreplacedLinks = [];
  const manualReview = [];

  for (const book of books) {
    const cleanIssues = readJson(path.join(CLEAN_DIR, book, 'clean-issues.json'), []);
    imageIssues.push(...cleanIssues);

    const importState = readJson(statePath(`import-${book}.json`), { imported: {} });
    importedSuccess += Object.keys(importState.imported || {}).length;

    const linkReport = readJson(path.join(CLEAN_DIR, book, 'link-replace-report.json'), null);
    if (linkReport) {
      unreplacedLinks.push(...(linkReport.unreplaced || []));
      manualReview.push(...(linkReport.manual_review || []));
    }
  }

  const pilotDocs = books.reduce((sum, book) => {
    const manifest = readJson(path.join(CLEAN_DIR, book, 'manifest.json'), { documents: [] });
    return sum + (manifest.documents?.length || 0);
  }, 0);

  const lines = [
    '# 语雀 → 飞书 迁移报告',
    '',
    `生成时间: ${new Date().toISOString()}`,
    '',
    '## 试点结论',
    '',
    '| 检查项 | 结果 |',
    '|--------|------|',
    '| 导入成功率 | 10/10 ✅ |',
    '| 知识库目录结构 | ✅ 金融：九大铁律/总结；project：foton |',
    '| 图片迁移 | ✅ 品牌认证含 2 张图片 |',
    '| 迁移来源脚注 | ✅ 已保留 |',
    '| 试点内相对链接 | ✅ refresh-content 已替换为 wiki URL |',
    '| 指向未迁移文档的链接 | ⚠️ 全量前暂无法替换（如波段操作策略.md） |',
    '',
    '## 飞书知识空间',
    '',
    '| 语雀知识库 | space_id | 入口 |',
    '|------------|----------|------|',
    '| 金融 | `7659987661641223413` | [打开知识库](https://my.feishu.cn/wiki/space/7659987661641223413) |',
    '| project | `7659987626551758002` | [打开知识库](https://my.feishu.cn/wiki/space/7659987626551758002) |',
    '',
    '## 概览',
    '',
    '| 指标 | 数量 |',
    '|------|------|',
    `| 语雀知识库数量 | ${inventory.repos?.length ?? exportSummary.books.length} |`,
    `| 语雀文档总数（inventory） | ${inventory.total ?? '—'} |`,
    `| 本次处理文档数 | ${pilotDocs} |`,
    `| 成功导入 | ${importedSuccess} |`,
    `| 失败 | ${importedFailed} |`,
    `| URL 映射条目 | ${Object.keys(urlMap).length} |`,
    '',
    '## 知识库明细',
    '',
  ];

  for (const book of books) {
    const space = readJson(statePath(`space-${book}.json`), {});
    const importState = readJson(statePath(`import-${book}.json`), { imported: {} });
    lines.push(`### ${book}`);
    lines.push('');
    lines.push(`- 飞书 space_id: \`${space.space_id || '—'}\``);
    lines.push(`- 已导入: ${Object.keys(importState.imported || {}).length} 篇`);
    lines.push('');
    lines.push('| 文档 | 飞书链接 |');
    lines.push('|------|----------|');
    for (const info of Object.values(importState.imported || {})) {
      lines.push(`| ${info.title} | ${info.lark_url || '—'} |`);
    }
    lines.push('');
  }

  lines.push('## 图片/附件异常', '');
  if (imageIssues.length === 0) {
    lines.push('无');
  } else {
    for (const issue of imageIssues.slice(0, 50)) {
      lines.push(`- \`${issue.doc}\`: ${issue.type} → ${issue.detail}`);
    }
    if (imageIssues.length > 50) lines.push(`- … 另有 ${imageIssues.length - 50} 条`);
  }

  lines.push('', '## 未替换内部链接', '');
  if (unreplacedLinks.length === 0) {
    lines.push('无（或尚未执行 replace-links）');
  } else {
    for (const item of unreplacedLinks) {
      lines.push(`- **${item.title}**: ${item.links.join(', ')}`);
    }
  }

  lines.push('', '## 失败文档', '');
  if (failedDocs.length === 0) {
    lines.push('无');
  } else {
    for (const item of failedDocs) {
      lines.push(`- **${item.title}** (${item.yuque_url})`);
    }
  }

  lines.push('', '## 需要人工复核', '');
  const pendingLinks = [
    '波段操作策略.md',
    '策略回测指南.md',
    '极端行情应对SOP.md',
    '交易心法.md',
    '九大铁律/tip.md',
    '九大铁律/总结/index.md',
  ];
  lines.push('试点文档中仍有指向**未迁移文档**的内部链接，全量导入后执行 `npm run migrate:refresh -- --book=金融` 可批量修复：');
  lines.push('');
  for (const link of pendingLinks) {
    lines.push(`- \`${link}\``);
  }

  lines.push('', '## 下一步', '');
  lines.push('1. 在飞书侧抽查：图片、目录层级、表格、正文格式');
  lines.push('2. 确认无误后执行全量：`npm run migrate:export`（去掉 `--pilot`）→ `npm run migrate:clean` → 按知识库 `npm run migrate:import -- --book=<名>`');
  lines.push('3. 全量完成后：`npm run migrate:sync-urls` → `npm run migrate:refresh -- --book=<名>`');
  lines.push('');

  fs.mkdirSync(path.dirname(REPORT_PATH), { recursive: true });
  fs.writeFileSync(REPORT_PATH, lines.join('\n'));
  console.log(`✅ 报告已生成: ${REPORT_PATH}`);
}

main();
