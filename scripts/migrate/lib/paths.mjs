import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { META_DIR, ROOT, getYuqueRoot, loadEnvLocal } from '../../lib/env.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export const MIGRATE_DIR = path.join(ROOT, '_migrate');
export const EXPORT_DIR = path.join(MIGRATE_DIR, 'export');
export const CLEAN_DIR = path.join(MIGRATE_DIR, 'clean');
export const STATE_DIR = path.join(MIGRATE_DIR, 'state');
export const FAILED_DOCS_PATH = path.join(MIGRATE_DIR, 'failed-docs.jsonl');
export const URL_MAP_PATH = path.join(MIGRATE_DIR, 'url-map.json');
export const REPORT_PATH = path.join(MIGRATE_DIR, 'migration-report.md');

export function ensureMigrateDirs() {
  for (const dir of [MIGRATE_DIR, EXPORT_DIR, CLEAN_DIR, STATE_DIR]) {
    fs.mkdirSync(dir, { recursive: true });
  }
}

export function bookExportDir(book) {
  return path.join(EXPORT_DIR, book);
}

export function bookCleanDir(book) {
  return path.join(CLEAN_DIR, book);
}

export function statePath(name) {
  return path.join(STATE_DIR, name);
}

export function readJson(filePath, fallback = null) {
  if (!fs.existsSync(filePath)) return fallback;
  return JSON.parse(fs.readFileSync(filePath, 'utf8'));
}

export function writeJson(filePath, data) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(data, null, 2));
}

export function appendJsonl(filePath, entry) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.appendFileSync(filePath, `${JSON.stringify(entry)}\n`);
}

export function getInventory() {
  const inventoryPath = path.join(META_DIR, 'inventory.json');
  if (!fs.existsSync(inventoryPath)) {
    throw new Error('未找到 _meta/inventory.json，请先运行 npm run sync-all && npm run inventory');
  }
  return readJson(inventoryPath);
}

export function yuqueDocUrl(doc) {
  if (doc.yuque_url) return doc.yuque_url;
  const group = doc.group || 'hanshihuanyan';
  const bookSlug = doc.book_slug || doc.book;
  const slug = doc.slug;
  if (!slug) return null;
  return `https://www.yuque.com/${group}/${bookSlug}/${slug}`;
}
