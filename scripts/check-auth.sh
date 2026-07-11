#!/usr/bin/env bash
# 检测语雀 Cookie 是否有效
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
YUQUE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$YUQUE_DIR/.env.local"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "❌ 未找到 $ENV_FILE，请复制 .env.local.example 并填入 Cookie"
  exit 1
fi

eval "$(
  node -e "
    const fs = require('fs');
    const env = {};
    for (const line of fs.readFileSync(process.argv[1], 'utf8').split('\n')) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) continue;
      const eq = trimmed.indexOf('=');
      if (eq === -1) continue;
      const key = trimmed.slice(0, eq).trim();
      let value = trimmed.slice(eq + 1).trim();
      if (
        (value.startsWith('\"') && value.endsWith('\"')) ||
        (value.startsWith(\"'\") && value.endsWith(\"'\"))
      ) {
        value = value.slice(1, -1);
      }
      if (key.startsWith('YUQUE_')) env[key] = value;
    }
    for (const [key, value] of Object.entries(env)) {
      process.stdout.write('export ' + key + '=' + JSON.stringify(value) + '\n');
    }
  " "$ENV_FILE"
)"

YUQUE_DATA_DIR="${YUQUE_DATA_DIR:-$YUQUE_DIR}"
if [[ "$YUQUE_DATA_DIR" != /* ]]; then
  YUQUE_DATA_DIR="$YUQUE_DIR/$YUQUE_DATA_DIR"
fi

STATUS_FILE="$YUQUE_DATA_DIR/_meta/cookie-status.json"

if [[ -z "${YUQUE_COOKIE:-}" && -z "${YUQUE_COOKIE_FULL:-}" ]]; then
  echo "❌ .env.local 中未配置 YUQUE_COOKIE 或 YUQUE_COOKIE_FULL"
  exit 1
fi

if [[ -n "${YUQUE_COOKIE_FULL:-}" ]]; then
  COOKIE_HEADER="$YUQUE_COOKIE_FULL"
elif [[ -n "${YUQUE_COOKIE:-}" ]]; then
  COOKIE_HEADER="_yuque_session=$YUQUE_COOKIE"
  if [[ -n "${YUQUE_CSRF_TOKEN:-}" ]]; then
    COOKIE_HEADER="$COOKIE_HEADER; yuque_ctoken=$YUQUE_CSRF_TOKEN"
  fi
  COOKIE_HEADER="$COOKIE_HEADER; lang=zh-cn"
else
  COOKIE_HEADER=""
fi

CSRF="${YUQUE_CSRF_TOKEN:-}"
if [[ -z "$CSRF" && "$COOKIE_HEADER" == *"yuque_ctoken="* ]]; then
  CSRF=$(echo "$COOKIE_HEADER" | sed -n 's/.*yuque_ctoken=\([^;]*\).*/\1/p')
fi

HEADERS=(-H "Cookie: $COOKIE_HEADER" -H "User-Agent: yuque-sync/1.0")
if [[ -n "$CSRF" ]]; then
  HEADERS+=(-H "x-csrf-token: $CSRF")
fi

RESP=$(curl -sS -w "\n%{http_code}" "${HEADERS[@]}" "https://www.yuque.com/api/v2/user")
HTTP_CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')

mkdir -p "$(dirname "$STATUS_FILE")"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

if [[ "$HTTP_CODE" == "200" ]]; then
  LOGIN=$(echo "$BODY" | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{try{const j=JSON.parse(d);console.log(j.data?.login||'unknown')}catch{console.log('unknown')}})")
  echo "{\"ok\":true,\"checked_at\":\"$TIMESTAMP\",\"login\":\"$LOGIN\",\"data_dir\":\"$YUQUE_DATA_DIR\"}" > "$STATUS_FILE"
  echo "✅ Cookie 有效，用户: $LOGIN"
  echo "   数据目录: $YUQUE_DATA_DIR"
  exit 0
fi

echo "{\"ok\":false,\"checked_at\":\"$TIMESTAMP\",\"http_code\":$HTTP_CODE,\"data_dir\":\"$YUQUE_DATA_DIR\"}" > "$STATUS_FILE"
if [[ "$HTTP_CODE" == "401" && "$COOKIE_HEADER" != *"_yuque_session="* ]]; then
  echo "❌ Cookie 无效 (HTTP 401)：缺少 _yuque_session"
  echo "   请在浏览器 F12 → Application → Cookies → yuque.com 复制完整 Cookie"
  echo "   须包含: _yuque_session=... 和 yuque_ctoken=..."
else
  echo "❌ Cookie 无效或已过期 (HTTP $HTTP_CODE)，请重新登录语雀并更新 .env.local"
fi
exit 1
