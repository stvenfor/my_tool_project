import fs from 'fs';
import path from 'path';
import {
  BACKUP_DIR,
  ensureDirs,
  getYuqueRoot,
  listRepoMirrorDirs,
  loadEnvLocal,
} from './env.mjs';

function walkFiles(dir, base = dir) {
  const results = [];
  if (!fs.existsSync(dir)) return results;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.name.startsWith('.') || entry.name === '_assets') continue;
    if (entry.isDirectory()) {
      results.push(...walkFiles(full, base));
    } else if (entry.isFile() && (entry.name.endsWith('.md') || entry.name.endsWith('.meta.json'))) {
      results.push(path.relative(base, full));
    }
  }
  return results;
}

function copyRecursive(src, dest) {
  fs.mkdirSync(dest, { recursive: true });
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    const srcPath = path.join(src, entry.name);
    const destPath = path.join(dest, entry.name);
    if (entry.isDirectory()) {
      copyRecursive(srcPath, destPath);
    } else {
      fs.copyFileSync(srcPath, destPath);
    }
  }
}

export function createBackup(label, bookFilter) {
  ensureDirs();
  const env = loadEnvLocal();
  const yuqueRoot = getYuqueRoot(env);
  let repos = listRepoMirrorDirs(env);
  if (bookFilter) {
    repos = repos.filter(r => r.book === bookFilter);
  }
  const stamp = label || new Date().toISOString().slice(0, 10);
  const backupRoot = path.join(BACKUP_DIR, stamp);

  if (repos.length === 0) {
    throw new Error(bookFilter ? `未找到知识库: ${bookFilter}` : `未找到知识库镜像: ${yuqueRoot}`);
  }

  const copiedBooks = [];
  for (const { book, mirrorDir } of repos) {
    const dest = path.join(backupRoot, book);
    copyRecursive(mirrorDir, dest);
    copiedBooks.push(book);
  }

  const manifest = {
    created_at: new Date().toISOString(),
    source_root: yuqueRoot,
    backup_root: backupRoot,
    books: copiedBooks,
    files: copiedBooks.flatMap(book =>
      walkFiles(path.join(backupRoot, book)).map(f => `${book}/${f}`),
    ),
  };
  fs.writeFileSync(path.join(backupRoot, 'manifest.json'), JSON.stringify(manifest, null, 2));
  return backupRoot;
}
