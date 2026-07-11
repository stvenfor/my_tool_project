#!/usr/bin/env node
/**
 * 引导配置语雀个人 Token
 */
import { execSync } from 'child_process';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const TOKEN_URL = 'https://www.yuque.com/settings/tokens';
const DASHBOARD_URL = 'https://www.yuque.com/dashboard';
const ENV_EXAMPLE = path.join(ROOT, '.env.local.example');
const ENV_FILE = path.join(ROOT, '.env.local');

console.log('\n📋 语雀工作区配置引导\n');
console.log(`工作目录: ${ROOT}\n`);
console.log('Cookie 方式已不稳定，推荐使用个人 Token：\n');
console.log(`  1. 登录 ${DASHBOARD_URL}`);
console.log(`  2. 打开 ${TOKEN_URL}`);
console.log('  3. 点击「新建」，勾选读写权限，复制 Token');
console.log('  4. 写入 .env.local：\n');
console.log('     YUQUE_PERSONAL_TOKEN=你的Token\n');

if (!fs.existsSync(ENV_FILE)) {
  if (fs.existsSync(ENV_EXAMPLE)) {
    fs.copyFileSync(ENV_EXAMPLE, ENV_FILE);
    console.log(`✅ 已创建 ${ENV_FILE}，请填入 YUQUE_PERSONAL_TOKEN\n`);
  }
} else {
  console.log(`ℹ️  配置文件已存在: ${ENV_FILE}\n`);
}

try {
  execSync(`open "${TOKEN_URL}"`, { stdio: 'ignore' });
  console.log('🌐 已在浏览器打开 Token 设置页\n');
} catch {
  console.log(`请手动打开: ${TOKEN_URL}\n`);
}

console.log('配置完成后运行:');
console.log('  npm run get-token   # 自动打开浏览器获取 Token（推荐）');
console.log('  npm run auth');
console.log('  npm run sync-all');
console.log('  npm run run-all\n');
