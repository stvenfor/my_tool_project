#!/usr/bin/env node
import fs from 'fs';
import path from 'path';
import {
  META_DIR,
  getCookieHeader,
  getPersonalToken,
  getYuqueRoot,
  loadEnvLocal,
  validateYuqueAuth,
} from './lib/env.mjs';
import { checkAuth } from './lib/yuque-api.mjs';

async function checkWithCookie(env) {
  const res = await fetch('https://www.yuque.com/api/mine', {
    headers: {
      Cookie: getCookieHeader(env),
      'User-Agent': 'yuque-sync/1.0',
    },
  });
  if (!res.ok) {
    return { ok: false, status: res.status };
  }
  const json = await res.json();
  return { ok: true, login: json?.data?.login || json?.data?.name, status: res.status };
}

async function main() {
  const env = loadEnvLocal();
  const authError = validateYuqueAuth(env);
  const dataDir = getYuqueRoot();
  const statusPath = path.join(META_DIR, 'cookie-status.json');
  fs.mkdirSync(path.dirname(statusPath), { recursive: true });
  const timestamp = new Date().toISOString();

  if (authError) {
    fs.writeFileSync(
      statusPath,
      JSON.stringify({ ok: false, checked_at: timestamp, error: authError, data_dir: dataDir }),
    );
    console.error(`❌ ${authError}`);
    console.error('\n运行: npm run get-token\n');
    process.exit(1);
  }

  const result = getPersonalToken(env)
    ? { ...(await checkAuth(env)), mode: 'token' }
    : { ...(await checkWithCookie(env)), mode: 'cookie' };

  if (result.ok) {
    fs.writeFileSync(
      statusPath,
      JSON.stringify({
        ok: true,
        checked_at: timestamp,
        login: result.login,
        mode: result.mode,
        data_dir: dataDir,
      }),
    );
    console.log(`✅ 认证有效 (${result.mode})，用户: ${result.login || '语雀用户'}`);
    console.log(`   数据目录: ${dataDir}`);
    process.exit(0);
  }

  fs.writeFileSync(
    statusPath,
    JSON.stringify({
      ok: false,
      checked_at: timestamp,
      error: result.error || `HTTP ${result.status}`,
      data_dir: dataDir,
    }),
  );
  console.error(`❌ 认证失败${result.status ? ` HTTP ${result.status}` : ''}，请重新运行: npm run get-token`);
  process.exit(1);
}

main();
