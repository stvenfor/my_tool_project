import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
export const ROOT = path.resolve(__dirname, '../..');
export const DEFAULT_YUQUE_DATA_DIR = ROOT;

const RESERVED_DIRS = new Set([
  '_meta',
  '_backup',
  '_reports',
  '_archive',
  '_migrate',
  'scripts',
  'node_modules',
  'inspection-form',
]);

function parseEnvFile(envPath) {
  if (!fs.existsSync(envPath)) {
    return null;
  }
  const env = {};
  for (const line of fs.readFileSync(envPath, 'utf8').split('\n')) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const eq = trimmed.indexOf('=');
    if (eq === -1) continue;
    const key = trimmed.slice(0, eq).trim();
    let value = trimmed.slice(eq + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    env[key] = value;
  }
  return env;
}

export function resolveEnvFilePath() {
  const candidates = [
    process.env.YUQUE_DATA_DIR && path.join(process.env.YUQUE_DATA_DIR, '.env.local'),
    path.join(ROOT, '.env.local'),
  ].filter(Boolean);
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }
  return path.join(ROOT, '.env.local');
}

export function loadEnvLocal() {
  const envPath = resolveEnvFilePath();
  return parseEnvFile(envPath) || {};
}

export function getYuqueRoot(env = loadEnvLocal()) {
  const dir = env.YUQUE_DATA_DIR || DEFAULT_YUQUE_DATA_DIR;
  if (path.isAbsolute(dir)) {
    return path.resolve(dir);
  }
  return path.resolve(ROOT, dir);
}

export function getYuquePaths(env = loadEnvLocal()) {
  const yuqueRoot = getYuqueRoot(env);
  return {
    YUQUE_ROOT: yuqueRoot,
    META_DIR: path.join(yuqueRoot, '_meta'),
    BACKUP_DIR: path.join(yuqueRoot, '_backup'),
    REPORTS_DIR: path.join(yuqueRoot, '_reports'),
    RULES_PATH: path.join(yuqueRoot, 'optimization-rules.yaml'),
  };
}

const paths = getYuquePaths();
export const YUQUE_ROOT = paths.YUQUE_ROOT;
export const META_DIR = paths.META_DIR;
export const BACKUP_DIR = paths.BACKUP_DIR;
export const REPORTS_DIR = paths.REPORTS_DIR;
export const RULES_PATH = paths.RULES_PATH;

export function getRepoConfig(env = loadEnvLocal()) {
  const repoUrl =
    env.YUQUE_REPO_URL || 'https://www.yuque.com/hanshihuanyan/eav1v0';
  const match = repoUrl.match(/yuque\.com\/([^/]+)\/([^/?#]+)/);
  if (!match) {
    throw new Error(`无效的 YUQUE_REPO_URL: ${repoUrl}`);
  }
  const yuqueRoot = getYuqueRoot(env);
  return {
    repoUrl,
    group: env.YUQUE_GROUP || match[1],
    book: env.YUQUE_BOOK || match[2],
    mirrorDir: path.join(yuqueRoot, env.YUQUE_BOOK || match[2]),
    yuqueRoot,
  };
}

export function listRepoMirrorDirs(env = loadEnvLocal()) {
  const yuqueRoot = getYuqueRoot(env);
  if (!fs.existsSync(yuqueRoot)) {
    return [];
  }
  return fs
    .readdirSync(yuqueRoot, { withFileTypes: true })
    .filter(
      entry =>
        entry.isDirectory() &&
        !entry.name.startsWith('.') &&
        !RESERVED_DIRS.has(entry.name),
    )
    .map(entry => ({
      book: entry.name,
      mirrorDir: path.join(yuqueRoot, entry.name),
    }));
}

export function getCookieHeader(env = loadEnvLocal()) {
  if (env.YUQUE_COOKIE_FULL) {
    return env.YUQUE_COOKIE_FULL;
  }
  if (env.YUQUE_COOKIE) {
    let cookie = `_yuque_session=${env.YUQUE_COOKIE}`;
    if (env.YUQUE_CSRF_TOKEN) {
      cookie += `; yuque_ctoken=${env.YUQUE_CSRF_TOKEN}`;
    }
    cookie += '; lang=zh-cn';
    return cookie;
  }
  return null;
}

export function getSessionValue(env = loadEnvLocal()) {
  if (env.YUQUE_COOKIE) {
    return env.YUQUE_COOKIE;
  }
  const cookie = getCookieHeader(env);
  if (!cookie) return null;
  const session = cookie.match(/_yuque_session=([^;]+)/)?.[1];
  return session || null;
}

export function validateYuqueAuth(env = loadEnvLocal()) {
  if (getPersonalToken(env)) {
    return null;
  }
  if (getSessionValue(env)) {
    return null;
  }
  return '未配置认证。请运行 npm run get-token 在浏览器登录并导出 Cookie';
}

export function getPersonalToken(env = loadEnvLocal()) {
  return env.YUQUE_PERSONAL_TOKEN || env.YUQUE_TOKEN || null;
}

export function getAuthMode(env = loadEnvLocal()) {
  return getPersonalToken(env) ? 'token' : 'cookie';
}

export function getCsrfToken(env = loadEnvLocal()) {
  if (env.YUQUE_CSRF_TOKEN) {
    return env.YUQUE_CSRF_TOKEN;
  }
  const full = env.YUQUE_COOKIE_FULL || '';
  const match = full.match(/(?:^|;\s*)yuque_ctoken=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

export const BOOK_SLUG_MAP = {
  金融: 'xk57o3',
  project: 'eav1v0',
};

export function slugToBookFolder(bookSlug, env = loadEnvLocal()) {
  for (const [folder, slug] of Object.entries(BOOK_SLUG_MAP)) {
    if (slug === bookSlug) return folder;
  }
  const inventoryPath = path.join(getYuquePaths(env).META_DIR, 'inventory.json');
  if (fs.existsSync(inventoryPath)) {
    const inventory = JSON.parse(fs.readFileSync(inventoryPath, 'utf8'));
    const found = inventory.documents?.find(d => d.book_slug === bookSlug);
    if (found?.book) return found.book;
  }
  return bookSlug;
}

export function resolveDocAbsPath(doc, env = loadEnvLocal()) {
  const yuqueRoot = getYuqueRoot(env);
  if (doc.mirror_dir && doc.inner_rel_path) {
    return path.join(doc.mirror_dir, doc.inner_rel_path);
  }
  if (doc.rel_path) {
    return path.join(yuqueRoot, doc.rel_path);
  }
  throw new Error(`无法解析文档路径: ${JSON.stringify(doc)}`);
}

export function ensureDirs() {
  const { META_DIR: meta, BACKUP_DIR: backup, REPORTS_DIR: reports, YUQUE_ROOT: root } =
    getYuquePaths();
  for (const dir of [root, meta, backup, path.join(reports, 'diff')]) {
    fs.mkdirSync(dir, { recursive: true });
  }
}
