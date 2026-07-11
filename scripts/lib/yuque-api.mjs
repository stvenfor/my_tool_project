import {
  getAuthMode,
  getCookieHeader,
  getCsrfToken,
  getPersonalToken,
  loadEnvLocal,
  validateYuqueAuth,
} from './env.mjs';

const API_BASE = 'https://www.yuque.com/api/v2';

export function buildAuthHeaders(env = loadEnvLocal()) {
  const token = getPersonalToken(env);
  if (token) {
    return {
      'X-Auth-Token': token,
      'User-Agent': 'yuque-sync/1.0',
      Accept: 'application/json',
    };
  }

  const cookie = getCookieHeader(env);
  if (!cookie) {
    throw new Error('未配置 YUQUE_PERSONAL_TOKEN 或 YUQUE_COOKIE');
  }
  const headers = {
    Cookie: cookie,
    'User-Agent': 'yuque-sync/1.0',
    Accept: 'application/json',
  };
  const csrf = getCsrfToken(env);
  if (csrf) {
    headers['x-csrf-token'] = csrf;
  }
  return headers;
}

async function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

export async function apiRequest(path, options = {}, retries = 3, env = loadEnvLocal()) {
  const url = `${API_BASE}${path}`;
  const headers = { ...buildAuthHeaders(env), ...(options.headers || {}) };

  for (let attempt = 0; attempt <= retries; attempt += 1) {
    const res = await fetch(url, { ...options, headers });
    if (res.status === 429 && attempt < retries) {
      await sleep(2000 * (attempt + 1));
      continue;
    }
    const text = await res.text();
    let data;
    try {
      data = text ? JSON.parse(text) : {};
    } catch {
      data = { raw: text };
    }
    return { ok: res.ok, status: res.status, data };
  }
  throw new Error(`请求失败: ${path}`);
}

export async function getCurrentUser(env = loadEnvLocal()) {
  return apiRequest('/user', {}, 3, env);
}

export async function getDoc(group, book, slug, env = loadEnvLocal()) {
  return apiRequest(`/repos/${group}/${book}/docs/${slug}`, {}, 3, env);
}

export async function updateDoc(group, book, slug, body, format = 'markdown', env = loadEnvLocal()) {
  return apiRequest(
    `/repos/${group}/${book}/docs/${slug}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ body, format }),
    },
    3,
    env,
  );
}

export async function listUserRepos(login, env = loadEnvLocal()) {
  const all = [];
  let offset = 0;
  const limit = 100;
  while (true) {
    const res = await apiRequest(
      `/users/${login}/repos?offset=${offset}&limit=${limit}`,
      {},
      3,
      env,
    );
    if (!res.ok) {
      throw new Error(`获取知识库列表失败 HTTP ${res.status}`);
    }
    const batch = res.data?.data || [];
    all.push(...batch);
    if (batch.length < limit) break;
    offset += limit;
  }
  return all;
}

export async function getRepoToc(bookId, env = loadEnvLocal()) {
  const res = await apiRequest(`/repos/${bookId}/toc`, {}, 3, env);
  if (!res.ok) {
    throw new Error(`获取目录失败 HTTP ${res.status}: book ${bookId}`);
  }
  return res.data?.data || [];
}

export async function getDocById(bookId, docId, env = loadEnvLocal()) {
  return apiRequest(`/repos/${bookId}/docs/${docId}`, {}, 3, env);
}

export async function checkAuth(env = loadEnvLocal()) {
  const authError = validateYuqueAuth(env);
  if (authError) {
    return { ok: false, status: 0, login: null, error: authError };
  }
  const res = await getCurrentUser(env);
  return {
    ok: res.ok,
    login: res.data?.data?.login,
    status: res.status,
    mode: getAuthMode(env),
    error: res.ok ? null : `HTTP ${res.status}`,
  };
}

export { sleep };
