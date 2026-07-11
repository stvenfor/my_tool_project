#!/usr/bin/env node
/**
 * 从已保存的浏览器登录态导出 Cookie（无需再次打开浏览器）
 * npm run export-cookie
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { chromium } from 'playwright';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const ENV_FILE = path.join(ROOT, '.env.local');
const PROFILE_DIR = path.join(ROOT, '_meta', 'browser-profile');

function upsertEnv(updates) {
  let content = fs.existsSync(ENV_FILE)
    ? fs.readFileSync(ENV_FILE, 'utf8')
    : fs.readFileSync(path.join(ROOT, '.env.local.example'), 'utf8');
  for (const [key, value] of Object.entries(updates)) {
    const line = `${key}=${value}`;
    const re = new RegExp(`^${key}=.*$`, 'm');
    content = re.test(content) ? content.replace(re, line) : `${line}\n${content}`;
  }
  fs.writeFileSync(ENV_FILE, content);
}

async function main() {
  if (!fs.existsSync(PROFILE_DIR)) {
    console.error('❌ 未找到浏览器登录态，请先运行: npm run get-token');
    process.exit(1);
  }

  const ctx = await chromium.launchPersistentContext(PROFILE_DIR, { headless: true });
  const page = ctx.pages()[0] || (await ctx.newPage());
  await page.goto('https://www.yuque.com/dashboard', { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(() => {});
  const check = await page.evaluate(async () => {
    const r = await fetch('/api/mine');
    if (!r.ok) return { ok: false, status: r.status };
    const j = await r.json();
    return { ok: true, login: j?.data?.login || j?.data?.name };
  });
  const cookies = await ctx.cookies('https://www.yuque.com');
  await ctx.close();

  const session = cookies.find(c => c.name === '_yuque_session')?.value;
  const ctoken = cookies.find(c => c.name === 'yuque_ctoken')?.value;
  if (!session || !check.ok) {
    console.error('❌ 登录已过期，请重新运行: npm run get-token');
    process.exit(1);
  }

  upsertEnv({
    YUQUE_COOKIE: session,
    ...(ctoken ? { YUQUE_CSRF_TOKEN: ctoken } : {}),
  });

  console.log(`✅ Cookie 已导出到 ${ENV_FILE}`);
  console.log(`   用户: ${check.login || '语雀用户'}`);
}

main();
