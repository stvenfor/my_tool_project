#!/usr/bin/env node
import { createBackup } from './lib/backup.mjs';

const label = process.argv.find(a => a.startsWith('--label='))?.split('=')[1];
const book = process.argv.find(a => a.startsWith('--book='))?.split('=')[1];

try {
  const backupPath = createBackup(label, book);
  console.log(`✅ 备份完成: ${backupPath}`);
} catch (err) {
  console.error(`❌ 备份失败: ${err.message}`);
  process.exit(1);
}
