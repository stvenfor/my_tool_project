#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import {
  gotoPage,
  isLoggedIn,
  launchPersistentPage,
  promptForEnter,
  resolveProfileDir,
} from "./douyin-browser.mjs";

const DEFAULT_VIDEO_UPLOAD_URL =
  "https://creator.douyin.com/creator-micro/content/upload";
const ALLOWED_EXT = new Set([".mp4", ".mov", ".m4v"]);
const MAX_TAGS = 5;
const MAX_TITLE_LEN = 30;

function printHelp() {
  console.log(`
Usage:
  node publish-video.mjs <video.json> [options]

Options:
  --dry-run         Fill form but do not publish
  --keep-open       Keep browser open after completion
  --skip-music      Skip automatic music selection
  --profile <dir>   Playwright profile directory
  --timeout <ms>    Navigation timeout (default: 60000)
  --headless        Run headless (not recommended)
  --help            Print this help
`);
}

function parseArgs(argv) {
  const args = {
    inputFile: "",
    pageUrl: process.env.DOUYIN_VIDEO_UPLOAD_URL ?? DEFAULT_VIDEO_UPLOAD_URL,
    timeoutMs: 60000,
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

function readVideoInput(inputFile) {
  if (!fs.existsSync(inputFile)) {
    throw new Error(`File not found: ${inputFile}`);
  }

  const parsed = JSON.parse(fs.readFileSync(inputFile, "utf8"));
  if (!parsed.videoPath) {
    throw new Error("videoPath is required");
  }

  return {
    videoPath: parsed.videoPath,
    title: parsed.title ?? "",
    description: parsed.description ?? "",
    tags: (parsed.tags ?? []).slice(0, MAX_TAGS),
    inputBaseDir: path.dirname(inputFile),
  };
}

function resolveVideoPath(videoPath, baseDir) {
  const resolved = path.isAbsolute(videoPath)
    ? videoPath
    : path.resolve(baseDir, videoPath);
  if (!fs.existsSync(resolved)) {
    throw new Error(`Video not found: ${resolved}`);
  }
  const ext = path.extname(resolved).toLowerCase();
  if (!ALLOWED_EXT.has(ext)) {
    throw new Error(`Unsupported video format ${ext}: ${resolved}`);
  }
  const stat = fs.statSync(resolved);
  if (stat.size > 128 * 1024 * 1024) {
    throw new Error(`Video exceeds 128MB: ${resolved}`);
  }
  return resolved;
}

function truncateTitle(title) {
  return [...title].slice(0, MAX_TITLE_LEN).join("");
}

function buildDescription(input) {
  const tagLine = input.tags.map((t) => `#${t.replace(/^#/, "")}`).join(" ");
  if (!input.description) return tagLine;
  if (!tagLine) return input.description;
  return `${input.description}\n\n${tagLine}`;
}

async function dismissPopups(page) {
  for (const text of ["我知道了", "确定", "知道了"]) {
    try {
      const btn = page.getByText(text, { exact: true }).first();
      if (await btn.isVisible({ timeout: 1000 })) {
        await btn.click();
        await page.waitForTimeout(300);
      }
    } catch {
      // ignore
    }
  }
}

async function selectHotMusic(page) {
  try {
    const musicBtn = page.getByText("选择音乐").first();
    if (!(await musicBtn.isVisible({ timeout: 3000 }))) {
      console.log("ℹ️ 未找到「选择音乐」，跳过");
      return;
    }
    console.log("🎵 选择热门音乐...");
    await musicBtn.click();
    await page.locator("text=推荐").first().waitFor({
      state: "visible",
      timeout: 15000,
    });
    await page.waitForTimeout(2000);

    const musicList = page.locator(".semi-tabs-pane-motion-overlay");
    await musicList.waitFor({ state: "visible", timeout: 10000 });
    const firstItem = musicList.locator('div:has-text("使用")').first();
    await firstItem.waitFor({ state: "visible", timeout: 10000 });
    await firstItem.hover();
    await page.waitForTimeout(500);
    await firstItem.getByRole("button", { name: "使用" }).click();
    await page.waitForTimeout(2000);
    console.log("✅ 已选择音乐");
  } catch (err) {
    console.log(`ℹ️ 音乐选择跳过: ${err.message}`);
  }
}

async function fillTitle(page, title) {
  const titleInput = page
    .locator('input[placeholder*="填写作品标题"], input[placeholder*="标题"]')
    .first();
  await titleInput.waitFor({ state: "visible", timeout: 30000 });
  await titleInput.click();
  await titleInput.fill(truncateTitle(title));
}

async function fillDescription(page, text) {
  const editor = page.locator(".zone-container").first();
  await editor.waitFor({ state: "visible", timeout: 30000 });
  await editor.click();
  await page.waitForTimeout(300);
  await page.keyboard.press("Control+a");
  await page.keyboard.press("Backspace");
  await page.keyboard.insertText(text);
}

async function selectAiCover(page) {
  try {
    await page.waitForTimeout(3000);
    const clicked = await page.evaluate(() => {
      const containers = document.querySelectorAll('[class*="recommendCover"]');
      for (const c of containers) {
        if (c.offsetParent && c.children.length > 0) {
          c.children[0].click();
          return true;
        }
      }
      return false;
    });
    if (!clicked) return;

    await page.waitForTimeout(2000);
    const confirm = page
      .locator('.semi-modal-wrap button:has-text("确定"), [role="dialog"] button:has-text("确定")')
      .first();
    if (await confirm.isVisible({ timeout: 3000 })) {
      await confirm.click();
      console.log("✅ 已选择 AI 推荐封面");
    }
  } catch {
    console.log("ℹ️ 封面选择跳过");
  }
}

async function setAiDeclaration(page) {
  try {
    const declBtn = page.getByText("添加声明").first();
    if (!(await declBtn.isVisible({ timeout: 3000 }))) return;

    await declBtn.click();
    await page.waitForTimeout(1500);

    const aiLabel = page
      .locator("label.semi-radio, label.semi-checkbox")
      .filter({ hasText: "内容由AI生成" })
      .first();
    if (await aiLabel.isVisible({ timeout: 3000 })) {
      await aiLabel.click({ force: true });
    }

    const confirm = page
      .locator('button:has-text("确定"), button:has-text("确认")')
      .first();
    if (await confirm.isVisible({ timeout: 3000 })) {
      await confirm.click();
      console.log("✅ 已添加 AI 声明");
    }
  } catch {
    console.log("ℹ️ AI 声明跳过");
  }
}

async function runPublishFlow(page, input, args) {
  const videoPath = resolveVideoPath(input.videoPath, input.inputBaseDir);

  console.log("打开视频上传页...");
  await gotoPage(page, args.pageUrl, args.timeoutMs);
  await dismissPopups(page);

  if (!(await isLoggedIn(page))) {
    console.log("未登录，请在浏览器中用手机抖音扫码登录（最多等待 3 分钟）...");
    let loggedIn = false;
    for (let i = 0; i < 90; i += 1) {
      await page.waitForTimeout(2000);
      if (await isLoggedIn(page)) {
        loggedIn = true;
        break;
      }
    }
    if (!loggedIn) {
      throw new Error("登录超时。请运行 node auth.mjs 完成扫码后再试");
    }
    console.log("✅ 登录成功");
    await gotoPage(page, args.pageUrl, args.timeoutMs);
    await dismissPopups(page);
  }

  console.log(`上传视频: ${path.basename(videoPath)}`);
  await page
    .locator('input[type="file"], button:has-text("上传视频")')
    .first()
    .waitFor({ state: "attached", timeout: 30000 });

  let uploaded = false;

  try {
    const [fileChooser] = await Promise.all([
      page.waitForEvent("filechooser", { timeout: 15000 }),
      page.getByRole("button", { name: "上传视频" }).click(),
    ]);
    await fileChooser.setFiles([videoPath]);
    uploaded = true;
  } catch {
    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.waitFor({ state: "attached", timeout: 30000 });
    await fileInput.setInputFiles([videoPath]);
    uploaded = true;
  }

  if (!uploaded) {
    throw new Error("无法找到视频上传入口");
  }

  console.log("⏳ 等待视频处理...");
  await page.waitForTimeout(12000);
  await dismissPopups(page);

  await page
    .locator('input[placeholder*="标题"], .zone-container')
    .first()
    .waitFor({ state: "visible", timeout: 120000 });

  if (input.title) {
    console.log("填写标题...");
    await fillTitle(page, input.title);
  }

  const desc = buildDescription(input);
  if (desc) {
    console.log("填写描述与话题...");
    await fillDescription(page, desc);
  }

  if (!args.skipMusic) {
    await selectHotMusic(page);
  }

  await selectAiCover(page);
  await setAiDeclaration(page);

  if (args.dryRun) {
    console.log("Dry run 完成，未点击发布。");
    await promptForEnter("按 Enter 关闭");
    return;
  }

  console.log("发布中...");
  const publishBtn = page.getByRole("button", { name: "发布", exact: true });
  await publishBtn.waitFor({ state: "visible", timeout: 30000 });
  await publishBtn.click();

  try {
    const confirmBtn = page.getByRole("button", { name: "确认发布" });
    await confirmBtn.waitFor({ state: "visible", timeout: 10000 });
    await confirmBtn.click();
  } catch {
    // some flows publish directly
  }

  await Promise.race([
    page.waitForURL(/manage/, { timeout: 60000 }),
    page.locator("text=发布成功").waitFor({ timeout: 60000 }),
    page.locator("text=审核中").waitFor({ timeout: 60000 }),
  ]).catch(() => {});

  console.log("🎉 视频已提交发布！");
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    printHelp();
    return;
  }
  if (!args.inputFile) {
    printHelp();
    throw new Error("Missing video.json path");
  }

  const input = readVideoInput(args.inputFile);
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
