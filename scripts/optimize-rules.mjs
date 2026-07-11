import fs from 'fs';
import path from 'path';
import { load as loadYaml } from 'js-yaml';
import {
  META_DIR,
  RULES_PATH,
  ensureDirs,
  getYuqueRoot,
  loadEnvLocal,
  resolveDocAbsPath,
} from './lib/env.mjs';

function loadRules() {
  if (!fs.existsSync(RULES_PATH)) {
    return { global: { rules: [] }, folders: {} };
  }
  return loadYaml(fs.readFileSync(RULES_PATH, 'utf8'));
}

function matchSkipPattern(relPath, patterns = []) {
  const normalized = relPath.replace(/\\/g, '/');
  for (const pattern of patterns) {
    const regex = new RegExp(
      '^' +
        pattern
          .replace(/[.+^${}()|[\]\\]/g, '\\$&')
          .replace(/\*/g, '.*') +
        '$',
      'i',
    );
    if (regex.test(normalized) || regex.test(path.basename(normalized))) {
      return true;
    }
  }
  return false;
}

function normalizeWhitespace(text) {
  return text.replace(/\r\n/g, '\n').replace(/[ \t]+$/gm, '');
}

function fixHeadingLevels(text) {
  const lines = text.split('\n');
  let lastLevel = 0;
  const out = [];

  for (const line of lines) {
    const m = line.match(/^(#{1,6})\s+(.+)$/);
    if (!m) {
      out.push(line);
      continue;
    }
    let level = m[1].length;
    if (lastLevel > 0 && level > lastLevel + 1) {
      level = lastLevel + 1;
      out.push(`${'#'.repeat(level)} ${m[2]}`);
    } else {
      out.push(line);
    }
    lastLevel = level;
  }
  return out.join('\n');
}

function codeBlockLang(text) {
  const lines = text.split('\n');
  let inBlock = false;
  return lines
    .map(line => {
      const openMatch = line.match(/^```(\w*)\s*$/);
      if (!openMatch) return line;
      if (!inBlock) {
        inBlock = true;
        return openMatch[1] ? line : '```text';
      }
      inBlock = false;
      return '```';
    })
    .join('\n');
}

function compressBlankLines(text) {
  return text.replace(/\n{3,}/g, '\n\n');
}

const RULE_FNS = {
  normalize_whitespace: normalizeWhitespace,
  fix_heading_levels: fixHeadingLevels,
  code_block_lang: codeBlockLang,
  compress_blank_lines: compressBlankLines,
};

function resolveFolderRules(folderPath, rulesConfig) {
  const globalRules = rulesConfig.global?.rules || [];
  const folderRules = rulesConfig.folders?.[folderPath]?.rules;
  if (folderRules) return folderRules;
  if (rulesConfig.folders?.['默认']?.rules) {
    return rulesConfig.folders['默认'].rules;
  }
  return globalRules;
}

function applyRules(content, ruleNames) {
  let result = content;
  for (const name of ruleNames) {
    const fn = RULE_FNS[name];
    if (fn) result = fn(result);
  }
  return result;
}

function main() {
  ensureDirs();
  const args = process.argv.slice(2);
  const folderFilter = args.find(a => a.startsWith('--folder='))?.split('=')[1];
  const bookFilter = args.find(a => a.startsWith('--book='))?.split('=')[1];
  const dryRun = args.includes('--dry-run');

  const env = loadEnvLocal();
  const yuqueRoot = getYuqueRoot(env);
  const inventoryPath = path.join(META_DIR, 'inventory.json');

  if (!fs.existsSync(inventoryPath)) {
    console.error('❌ 未找到 inventory.json，请先运行 npm run inventory');
    process.exit(1);
  }

  const { documents } = JSON.parse(fs.readFileSync(inventoryPath, 'utf8'));
  const rulesConfig = loadRules();
  const skipPatterns = rulesConfig.global?.skip_patterns || [];
  let changed = 0;

  for (const doc of documents) {
    if (!doc.optimizable) continue;
    if (bookFilter && doc.book !== bookFilter) {
      continue;
    }
    if (folderFilter && doc.folder_path !== folderFilter && doc.folder_path !== folderFilter.replace(/^\//, '')) {
      continue;
    }
    if (matchSkipPattern(doc.rel_path, skipPatterns)) continue;

    const absPath = resolveDocAbsPath(doc, env);
    if (!fs.existsSync(absPath)) continue;

    const original = fs.readFileSync(absPath, 'utf8');
    const ruleNames = resolveFolderRules(doc.folder_path || '默认', rulesConfig);
    const optimized = applyRules(original, ruleNames);

    if (optimized !== original) {
      changed += 1;
      if (!dryRun) {
        fs.writeFileSync(absPath, optimized);
      }
      console.log(`${dryRun ? '[dry-run] ' : ''}✏️  ${doc.rel_path}`);
    }
  }

  const logPath = path.join(META_DIR, 'optimize-log.json');
  const entry = {
    at: new Date().toISOString(),
    folder_filter: folderFilter || null,
    book_filter: bookFilter || null,
    dry_run: dryRun,
    changed,
  };
  const prev = fs.existsSync(logPath)
    ? JSON.parse(fs.readFileSync(logPath, 'utf8'))
    : { runs: [] };
  prev.runs.push(entry);
  fs.writeFileSync(logPath, JSON.stringify(prev, null, 2));

  console.log(`✅ 规则优化完成，变更 ${changed} 篇`);
}

main();
