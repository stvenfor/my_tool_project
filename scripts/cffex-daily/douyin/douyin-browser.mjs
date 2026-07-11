import os from "node:os";
import path from "node:path";
import process from "node:process";
import readline from "node:readline/promises";
import { chromium } from "playwright";

export const DEFAULT_UPLOAD_URL =
  "https://creator.douyin.com/creator-micro/content/upload?default-tab=3";

export const DEFAULT_USER_DATA_DIR = path.join(
  os.homedir(),
  ".douyin-playwright",
  "profile"
);

const DEFAULT_VIEWPORT = { width: 1440, height: 1200 };

export function resolveProfileDir(override) {
  if (override) return path.resolve(override);
  if (process.env.DOUYIN_PROFILE_DIR) {
    return path.resolve(process.env.DOUYIN_PROFILE_DIR);
  }
  return DEFAULT_USER_DATA_DIR;
}

export async function promptForEnter(message) {
  const terminal = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });

  try {
    await terminal.question(`${message}\n`);
  } finally {
    terminal.close();
  }
}

export async function launchPersistentPage(options = {}) {
  const {
    userDataDir = DEFAULT_USER_DATA_DIR,
    headless = false,
    viewport = DEFAULT_VIEWPORT,
    alwaysNewPage = false,
  } = options;

  const context = await chromium.launchPersistentContext(userDataDir, {
    headless,
    channel: "chrome",
    viewport,
    args: ["--disable-blink-features=AutomationControlled"],
  });

  const page = alwaysNewPage
    ? await context.newPage()
    : (context.pages()[0] ?? (await context.newPage()));

  await page.bringToFront().catch(() => {});

  return { context, page };
}

export async function gotoPage(page, pageUrl, navigationTimeoutMs = 60000) {
  await page.goto(pageUrl, {
    waitUntil: "domcontentloaded",
    timeout: navigationTimeoutMs,
  });
  await page.bringToFront().catch(() => {});
}

export async function isLoggedIn(page) {
  if (/login/i.test(page.url())) return false;
  try {
    await page
      .getByRole("button", { name: "上传视频" })
      .first()
      .waitFor({ state: "visible", timeout: 5000 });
    return true;
  } catch {
    try {
      const loginHint = page.locator("text=扫码登录").first();
      await loginHint.waitFor({ state: "visible", timeout: 2000 });
      return false;
    } catch {
      return false;
    }
  }
}
