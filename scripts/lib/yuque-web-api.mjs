import fs from 'fs';
import path from 'path';
import { chromium } from 'playwright';
import { META_DIR, ROOT, getPersonalToken, loadEnvLocal } from './env.mjs';

const PROFILE_DIR = path.join(ROOT, '_meta', 'browser-profile');
const BOOK_IDS_PATH = path.join(META_DIR, 'book-ids.json');

let browserContext = null;

function loadBookIds() {
  if (!fs.existsSync(BOOK_IDS_PATH)) return {};
  return JSON.parse(fs.readFileSync(BOOK_IDS_PATH, 'utf8'));
}

function saveBookIds(map) {
  fs.mkdirSync(META_DIR, { recursive: true });
  fs.writeFileSync(BOOK_IDS_PATH, JSON.stringify(map, null, 2));
}

export async function getBrowserContext() {
  if (browserContext) return browserContext;
  fs.mkdirSync(PROFILE_DIR, { recursive: true });
  browserContext = await chromium.launchPersistentContext(PROFILE_DIR, {
    headless: true,
    locale: 'zh-CN',
  });
  return browserContext;
}

export async function closeBrowserContext() {
  if (browserContext) {
    await browserContext.close();
    browserContext = null;
  }
}

export function useWebPush(env = loadEnvLocal()) {
  return !getPersonalToken(env);
}

async function getPage() {
  const ctx = await getBrowserContext();
  const page = ctx.pages()[0] || (await ctx.newPage());
  await page.goto('https://www.yuque.com/dashboard', {
    waitUntil: 'domcontentloaded',
    timeout: 60000,
  }).catch(() => {});
  return page;
}

export async function resolveBookId(group, bookSlug) {
  const key = `${group}/${bookSlug}`;
  const cached = loadBookIds()[key];
  if (cached) return cached;

  const page = await getPage();
  let bookId = null;
  const handler = response => {
    const match = response.url().match(/\/api\/books\/(\d+)\/overview/);
    if (match) bookId = Number(match[1]);
  };
  page.on('response', handler);
  await page.goto(`https://www.yuque.com/${group}/${bookSlug}`, {
    waitUntil: 'domcontentloaded',
    timeout: 60000,
  }).catch(() => {});
  await page.waitForTimeout(2000);
  page.off('response', handler);

  if (!bookId) {
    throw new Error(`无法解析知识库 ID: ${key}，请运行 npm run get-token 重新登录`);
  }

  const map = loadBookIds();
  map[key] = bookId;
  saveBookIds(map);
  return bookId;
}

export async function getDocWeb(group, bookSlug, slug, { edit = false } = {}) {
  const bookId = await resolveBookId(group, bookSlug);
  const page = await getPage();
  return page.evaluate(
    async ({ slug: docSlug, bookId: id, edit: editMode }) => {
      const query = editMode
        ? `book_id=${id}&mode=edit&merge_dynamic_data=1`
        : `include_contributors=false&book_id=${id}`;
      const res = await fetch(`/api/docs/${docSlug}?${query}`);
      const json = await res.json().catch(() => ({}));
      return { ok: res.ok, status: res.status, data: json.data };
    },
    { slug, bookId, edit },
  );
}

export async function updateDocWeb(docId, payload) {
  const page = await getPage();
  return page.evaluate(
    async ({ id, payload: bodyPayload }) => {
      const res = await fetch(`/api/docs/${id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'x-requested-with': 'XMLHttpRequest',
        },
        body: JSON.stringify(bodyPayload),
      });
      const text = await res.text();
      let data;
      try {
        data = text ? JSON.parse(text) : {};
      } catch {
        data = { raw: text };
      }
      return { ok: res.ok, status: res.status, data };
    },
    { id: docId, payload },
  );
}

export async function listDocVersionsWeb(docId, limit = 100) {
  const page = await getPage();
  return page.evaluate(
    async ({ id, limit: n }) => {
      const res = await fetch(`/api/doc_versions?doc_id=${id}&limit=${n}`);
      const json = await res.json().catch(() => ({}));
      return { ok: res.ok, status: res.status, data: json.data || [] };
    },
    { id: docId, limit },
  );
}

export async function getDocVersionWeb(versionId) {
  const page = await getPage();
  return page.evaluate(async id => {
    const res = await fetch(`/api/doc_versions/${id}`);
    const json = await res.json().catch(() => ({}));
    return { ok: res.ok, status: res.status, data: json.data };
  }, versionId);
}

export async function deleteDocWeb(docId) {
  const page = await getPage();
  return page.evaluate(async id => {
    const res = await fetch(`/api/docs/${id}`, {
      method: 'DELETE',
      headers: { 'x-requested-with': 'XMLHttpRequest' },
    });
    const text = await res.text();
    let data;
    try {
      data = text ? JSON.parse(text) : {};
    } catch {
      data = { raw: text };
    }
    return { ok: res.ok, status: res.status, data };
  }, docId);
}

export async function createDocWeb(group, bookSlug, { title, body, format = 'markdown' }) {
  const bookId = await resolveBookId(group, bookSlug);
  const page = await getPage();
  return page.evaluate(
    async ({ id, payload }) => {
      const res = await fetch('/api/docs', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-requested-with': 'XMLHttpRequest',
        },
        body: JSON.stringify({
          book_id: id,
          title: payload.title,
          format: payload.format,
          body: payload.body,
          public: 0,
        }),
      });
      const text = await res.text();
      let data;
      try {
        data = text ? JSON.parse(text) : {};
      } catch {
        data = { raw: text };
      }
      return { ok: res.ok, status: res.status, data };
    },
    { id: bookId, payload: { title, body, format } },
  );
}

export async function checkWebSession() {
  const page = await getPage();
  return page.evaluate(async () => {
    const res = await fetch('/api/mine');
    if (!res.ok) return { ok: false, status: res.status };
    const json = await res.json();
    return { ok: true, login: json?.data?.login, status: res.status };
  });
}
