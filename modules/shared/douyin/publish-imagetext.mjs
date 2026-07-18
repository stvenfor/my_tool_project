#!/usr/bin/env node
/**
 * Publish Douyin image-text (图文). Uses footer 「发布」 button —
 * never the landing-page 「高清发布」 which aborts the editor flow.
 */
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import {
  gotoPage,
  launchPersistentPage,
  promptForEnter,
  resolveProfileDir,
} from "./douyin-browser.mjs";

const DEFAULT_UPLOAD_URL =
  "https://creator.douyin.com/creator-micro/content/upload?default-tab=3";
const ALLOWED_EXT = new Set([".png", ".jpg", ".jpeg", ".webp"]);
const MAX_IMAGES = 30;
const MAX_TAGS = 5;

function printHelp() {
  console.log(`
Usage:
  node publish-imagetext.mjs <imagetext.json> [options]

Options:
  --dry-run         Fill form but do not publish
  --keep-open       Keep browser open after completion
  --skip-music      Skip automatic music selection
  --profile <dir>   Playwright profile directory
  --timeout <ms>    Navigation timeout (default: 90000)
  --headless        Run headless (not recommended)
  --url <url>       Override upload page URL
  --help            Print this help
`);
}

function parseArgs(argv) {
  const args = {
    inputFile: "",
    pageUrl: process.env.DOUYIN_UPLOAD_URL ?? DEFAULT_UPLOAD_URL,
    timeoutMs: 90000,
    profileDir: resolveProfileDir(),
    dryRun: false,
    keepOpen: false,
    skipMusic: false,
    headless: false,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    switch (arg) {
      case "--help":
      case "-h":
        args.help = true;
        break;
      case "--dry-run":
        args.dryRun = true;
        break;
      case "--keep-open":
        args.keepOpen = true;
        break;
      case "--skip-music":
        args.skipMusic = true;
        break;
      case "--headless":
        args.headless = true;
        break;
      case "--profile":
        args.profileDir = path.resolve(argv[++i] ?? args.profileDir);
        break;
      case "--timeout":
        args.timeoutMs = Number(argv[++i]);
        break;
      case "--url":
        args.pageUrl = argv[++i] ?? args.pageUrl;
        break;
      default:
        if (!arg.startsWith("-") && !args.inputFile) {
          args.inputFile = path.resolve(arg);
          break;
        }
        throw new Error(`Unknown argument: ${arg}`);
    }
  }
  return args;
}

function readInput(inputFile) {
  if (!fs.existsSync(inputFile)) {
    throw new Error(`File not found: ${inputFile}`);
  }
  const raw = JSON.parse(fs.readFileSync(inputFile, "utf8"));
  const base = path.dirname(inputFile);
  const imagePaths = (raw.imagePaths || []).map((p) =>
    path.isAbsolute(p) ? p : path.resolve(base, p)
  );
  if (!imagePaths.length) throw new Error("imagePaths is required");
  if (imagePaths.length > MAX_IMAGES) {
    throw new Error(`Too many images (max ${MAX_IMAGES})`);
  }
  for (const p of imagePaths) {
    if (!fs.existsSync(p)) throw new Error(`Image not found: ${p}`);
    const ext = path.extname(p).toLowerCase();
    if (!ALLOWED_EXT.has(ext)) {
      throw new Error(`Unsupported image type: ${ext} (${p})`);
    }
  }
  const tags = (raw.tags || [])
    .slice(0, MAX_TAGS)
    .map((t) => String(t).replace(/^#/, ""));
  let description = String(raw.description || "").trim();
  if (tags.length) {
    const tagLine = tags.map((t) => `#${t}`).join(" ");
    description = description ? `${description}\n\n${tagLine}` : tagLine;
  }
  const title =
    String(raw.title || "").trim() ||
    description.split("\n").find((l) => l.trim())?.trim().slice(0, 30) ||
    "中信期货净持仓";
  return { imagePaths, description, title };
}

async function uploadImages(page, images) {
  const [chooser] = await Promise.all([
    page.waitForEvent("filechooser", { timeout: 20000 }),
    page.getByRole("button", { name: "上传图文" }).first().click(),
  ]);
  await chooser.setFiles(images);
}

async function selectHotMusic(page) {
  try {
    await page.getByText("选择音乐").nth(1).click({ timeout: 3000 });
    const musicList = page.locator(".semi-tabs-pane-motion-overlay").first();
    await musicList.waitFor({ state: "visible", timeout: 8000 });
    const firstItem = musicList.locator('div:has-text("使用")').first();
    await firstItem.hover();
    await firstItem.getByRole("button", { name: "使用" }).click();
    console.log("✅ 已选择音乐");
  } catch {
    console.log("ℹ️ 选音乐跳过");
  }
}

async function addAiDeclaration(page) {
  try {
    await page.getByText("添加声明").first().click({ timeout: 2500 });
    await page.waitForTimeout(600);
    await page.locator("text=内容由AI生成").first().click({ timeout: 3000 });
    await page
      .getByRole("button", { name: /确定|完成/ })
      .first()
      .click({ timeout: 2500 })
      .catch(() => {});
    console.log("✅ AI 声明");
  } catch {
    console.log("ℹ️ AI 声明跳过");
  }
}

async function runPublishFlow(page, input, args) {
  console.log("打开上传页...");
  await gotoPage(page, args.pageUrl, args.timeoutMs);
  await page.waitForTimeout(1200);

  console.log(`上传 ${input.imagePaths.length} 张图片...`);
  await uploadImages(page, input.imagePaths);
  await page.waitForURL(/post\/image/, { timeout: 120000 });
  await page.waitForTimeout(3500);
  console.log("editor url:", page.url());

  try {
    const titleInput = page
      .locator('input[placeholder*="标题"], textarea[placeholder*="标题"]')
      .first();
    await titleInput.waitFor({ state: "visible", timeout: 2500 });
    await titleInput.click();
    await titleInput.fill(input.title);
    console.log("填写标题:", input.title);
  } catch {
    console.log("无独立标题框，跳过");
  }

  if (input.description) {
    console.log("填写描述...");
    const editor = page.locator(".zone-container").first();
    await editor.click({ timeout: 20000 });
    await page.waitForTimeout(300);
    await page.keyboard.press(
      process.platform === "darwin" ? "Meta+A" : "Control+A"
    );
    await page.keyboard.insertText(input.description);
    await page.waitForTimeout(1000);
  }

  if (!args.skipMusic) {
    await selectHotMusic(page);
  }
  await addAiDeclaration(page);

  if (args.dryRun) {
    console.log("Dry run 完成，未点击发布。");
    await promptForEnter("按 Enter 关闭");
    return;
  }

  console.log("点击发布...");
  // Footer primary 「发布」 only — do NOT click 「高清发布」
  const publishBtn = page
    .locator("button.button-dhlUZE.primary-cECiOJ")
    .filter({ hasText: /^发布$/ })
    .first();
  await publishBtn.waitFor({ state: "visible", timeout: 15000 });
  if (await publishBtn.isDisabled()) {
    throw new Error("发布按钮 disabled");
  }
  await publishBtn.click();

  for (const name of ["确认发布", "确认"]) {
    try {
      const btn = page.getByRole("button", { name, exact: true }).first();
      await btn.waitFor({ state: "visible", timeout: 4000 });
      await btn.click();
      console.log("clicked", name);
      break;
    } catch {
      /* optional modal */
    }
  }

  const signal = await Promise.race([
    page
      .waitForURL(/manage|content\/manage/, { timeout: 90000 })
      .then(() => "manage-url"),
    page
      .locator("text=发布成功")
      .first()
      .waitFor({ timeout: 90000 })
      .then(() => "发布成功"),
    page
      .locator("text=作品管理")
      .first()
      .waitFor({ timeout: 90000 })
      .then(() => "作品管理"),
  ]).catch(() => null);

  if (!signal) {
    throw new Error(`未能确认发布成功 (url=${page.url()})`);
  }
  console.log("🎉 发布成功！signal=", signal, "url=", page.url());
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    printHelp();
    return;
  }
  if (!args.inputFile) {
    printHelp();
    throw new Error("Missing imagetext.json path");
  }

  const input = readInput(args.inputFile);
  const { context, page } = await launchPersistentPage({
    headless: args.headless,
    userDataDir: args.profileDir,
  });

  try {
    await runPublishFlow(page, input, args);
  } finally {
    if (!args.keepOpen) {
      await context.close();
    }
  }
}

main().catch((err) => {
  console.error(err instanceof Error ? err.stack ?? err.message : String(err));
  process.exit(1);
});
