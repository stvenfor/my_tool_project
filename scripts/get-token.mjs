#!/usr/bin/env node
/**
 * 从浏览器登录态导出 Cookie 到 .env.local（无需超级会员 Token）
 * npm run get-token
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { chromium } from 'playwright';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const ENV_FILE = path.join(ROOT, '.env.local');
const PROFILE_DIR = path.join(ROOT, '_meta', 'browser-profile');
const DASHBOARD_URL = 'https://www.yuque.com/dashboard';
const TOKEN_URL = 'https://www.yuque.com/settings/tokens';
const LOGIN_TIMEOUT_MS = 5 * 60 * 1000;

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

function buildCookieHeader(cookies) {
  return cookies
    .filter(c => c.domain.includes('yuque.com'))
    .map(c => `${c.name}=${c.value}`)
    .join('; ');
}

async function safeGoto(page, url) {
  try {
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
  } catch (err) {
    if (!String(err.message).includes('ERR_ABORTED')) throw err;
  }
}

async function waitForDashboard(page) {
  await safeGoto(page, DASHBOARD_URL);
  const start = Date.now();
  while (Date.now() - start < LOGIN_TIMEOUT_MS) {
    const url = page.url();
    const title = await page.title().catch(() => '');
    if (url.includes('/dashboard') && title.includes('工作台')) {
      return true;
    }
    if (url.includes('login') || url.includes('passport')) {
      console.log('   → 请在浏览器窗口中登录语雀（扫码/手机号）...');
    }
    await page.waitForTimeout(2000);
  }
  return false;
}

async function verifySession(page) {
  return page.evaluate(async () => {
    const res = await fetch('/api/mine');
    if (!res.ok) return { ok: false, status: res.status };
    const json = await res.json();
    return { ok: true, login: json?.data?.login || json?.data?.name, status: res.status };
  });
}

async function tryCreatePersonalToken(page) {
  await safeGoto(page, TOKEN_URL);
  await page.waitForTimeout(1500);
  const body = await page.locator('body').innerText();
  if (/超级会员|立即购买/.test(body) && !/暂无数据/.test(body)) {
    return { blocked: true, reason: 'Personal Token 需要语雀超级会员' };
  }
  const btn = page.getByRole('button', { name: /新建/i }).first();
  if (!(await btn.isVisible({ timeout: 3000 }).catch(() => false))) {
    return { blocked: true, reason: '未找到 Token 新建按钮（可能需要超级会员）' };
  }
  return { blocked: false };
}

async function main() {
  fs.mkdirSync(PROFILE_DIR, { recursive: true });

  console.log('\n🔐 语雀登录凭证获取\n');
  console.log('说明：语雀 Personal Token 需要超级会员，本工具改用浏览器 Cookie 同步。\n');
  console.log('即将打开浏览器，请登录 https://www.yuque.com/dashboard\n');

  const context = await chromium.launchPersistentContext(PROFILE_DIR, {
    headless: false,
    viewport: { width: 1280, height: 800 },
    locale: 'zh-CN',
  });

  const page = context.pages()[0] || (await context.newPage());

  try {
    console.log('⏳ 等待登录（最多 5 分钟）...');
    const loggedIn = await waitForDashboard(page);
    if (!loggedIn) {
      throw new Error('登录超时，请重新运行 npm run get-token');
    }

    const sessionCheck = await verifySession(page);
    if (!sessionCheck.ok) {
      throw new Error(`登录态无效 HTTP ${sessionCheck.status}`);
    }
    console.log(`✅ 已登录: ${sessionCheck.login || '语雀用户'}`);

    const tokenAttempt = await tryCreatePersonalToken(page);
    if (tokenAttempt.blocked) {
      console.log(`ℹ️  ${tokenAttempt.reason}，改用 Cookie 方式`);
    }

    const cookies = await context.cookies('https://www.yuque.com');
    const session = cookies.find(c => c.name === '_yuque_session')?.value;
    const ctoken = cookies.find(c => c.name === 'yuque_ctoken')?.value;

    if (!session) {
      throw new Error('未找到 _yuque_session，请重新登录');
    }

    upsertEnv({
      YUQUE_COOKIE: session,
      ...(ctoken ? { YUQUE_CSRF_TOKEN: ctoken } : {}),
      YUQUE_PERSONAL_TOKEN: '',
    });

    // 移除空的 PERSONAL_TOKEN 行
    let envContent = fs.readFileSync(ENV_FILE, 'utf8');
    envContent = envContent.replace(/^YUQUE_PERSONAL_TOKEN=\s*\n/m, '');
    fs.writeFileSync(ENV_FILE, envContent);

    console.log(`\n✅ Cookie 已写入 ${ENV_FILE}`);
    console.log('   接下来运行:\n');
    console.log('   npm run auth');
    console.log('   npm run sync-all');
    console.log('   npm run run-all\n');
  } finally {
    await context.close();
  }
}

main().catch(err => {
  console.error(`\n❌ ${err.message}\n`);
  process.exit(1);
});
