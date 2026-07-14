#!/usr/bin/env node

import path from "node:path";
import process from "node:process";
import {
  DEFAULT_UPLOAD_URL,
  gotoPage,
  isLoggedIn,
  launchPersistentPage,
  promptForEnter,
  resolveProfileDir,
} from "./douyin-browser.mjs";

function printHelp() {
  console.log(`
Usage:
  node auth.mjs [options]

Options:
  --url <url>       Login page URL (default: imagetext upload page)
  --profile <dir>   Playwright profile directory
  --timeout <ms>    Navigation timeout (default: 60000)
  --help            Print this help
`);
}

function parseArgs(argv) {
  const args = {
    pageUrl: process.env.DOUYIN_UPLOAD_URL ?? DEFAULT_UPLOAD_URL,
    profileDir: resolveProfileDir(),
    timeoutMs: 60000,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    switch (arg) {
      case "--help":
      case "-h":
        args.help = true;
        break;
      case "--url":
        args.pageUrl = argv[++i] ?? args.pageUrl;
        break;
      case "--profile":
        args.profileDir = path.resolve(argv[++i] ?? args.profileDir);
        break;
      case "--timeout":
        args.timeoutMs = Number(argv[++i]);
        break;
      default:
        throw new Error(`Unknown argument: ${arg}`);
    }
  }

  return args;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    printHelp();
    return;
  }

  const { context, page } = await launchPersistentPage({
    userDataDir: args.profileDir,
  });

  try {
    await gotoPage(page, args.pageUrl, args.timeoutMs);
    console.log(`已打开：${args.pageUrl}`);
    console.log(`登录态保存目录：${args.profileDir}`);
    console.log("请在浏览器中用手机抖音 App 扫码登录。");
    await promptForEnter("登录完成后按 Enter 保存并关闭");

    await gotoPage(page, args.pageUrl, args.timeoutMs).catch(() => {});
    if (await isLoggedIn(page)) {
      console.log("✅ 登录态已保存，后续发布命令将复用此 Profile。");
    } else {
      console.log(
        "⚠️ Profile 已保存，但未确认登录成功。若发布时仍跳转登录页，请重新运行 node auth.mjs。"
      );
    }
  } finally {
    await context.close();
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack ?? error.message : String(error));
  process.exitCode = 1;
});
