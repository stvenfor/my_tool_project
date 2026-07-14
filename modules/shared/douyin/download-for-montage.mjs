#!/usr/bin/env node
/** Download Douyin share URL to mp4 using logged-in playwright profile. */
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { chromium } from "playwright";

const DOUYIN_PROFILE = path.join(os.homedir(), ".douyin-playwright", "profile");

function parseArgs(argv) {
  const args = { url: "", output: "" };
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i] === "--url") args.url = argv[++i];
    else if (argv[i] === "--output") args.output = argv[++i];
  }
  return args;
}

async function resolveVideoUrl(page, shareUrl) {
  const directVideoId = shareUrl.match(/\/video\/(\d+)/)?.[1];
  const targetUrl = directVideoId
    ? `https://www.douyin.com/video/${directVideoId}`
    : shareUrl;

  for (let attempt = 0; attempt < 2; attempt += 1) {
    await page.goto(targetUrl, { waitUntil: "domcontentloaded", timeout: 90000 });
    await page.waitForTimeout(2500);

    if (!page.url().includes("/video/")) {
      await page.waitForURL(/\/video\//, { timeout: 30000 }).catch(() => {});
    }
    if (page.url().includes("/jingxuan") && directVideoId) {
      await page.goto(`https://www.douyin.com/video/${directVideoId}`, {
        waitUntil: "domcontentloaded",
        timeout: 90000,
      });
      await page.waitForTimeout(2000);
    }

    await page.waitForSelector("video", { timeout: 30000 }).catch(() => {});
    await page.waitForTimeout(1500);

    const videoSrc = await page.evaluate(() => {
      const videos = [...document.querySelectorAll("video")];
      const candidates = videos
        .map((v) => v.src || v.currentSrc || "")
        .filter((src) => src.includes("douyinvod") || src.includes(".mp4"));
      candidates.sort((a, b) => b.length - a.length);
      return candidates[0] || "";
    });

    if (videoSrc) {
      return { videoSrc, pageUrl: page.url() };
    }
    if (attempt === 0) {
      await page.waitForTimeout(2000);
    }
  }

  throw new Error(`No video src found for ${shareUrl} (final: ${page.url()})`);
}

async function main() {
  const { url, output } = parseArgs(process.argv.slice(2));
  if (!url || !output) {
    console.error("Usage: node download-for-montage.mjs --url <url> --output <path.mp4>");
    process.exit(1);
  }

  fs.mkdirSync(path.dirname(path.resolve(output)), { recursive: true });

  const context = await chromium.launchPersistentContext(DOUYIN_PROFILE, {
    headless: true,
    channel: "chrome",
    args: ["--disable-blink-features=AutomationControlled"],
  });

  try {
    const page = context.pages()[0] ?? (await context.newPage());
    const { videoSrc, pageUrl } = await resolveVideoUrl(page, url);
    console.log(`Resolved: ${pageUrl}`);

    const response = await context.request.get(videoSrc, {
      headers: { Referer: "https://www.douyin.com/" },
    });
    if (!response.ok()) {
      throw new Error(`Download failed: HTTP ${response.status()}`);
    }
    const body = await response.body();
    if (body.length < 10000) {
      throw new Error(`Download too small (${body.length} bytes)`);
    }
    fs.writeFileSync(output, body);
    console.log(`Saved: ${output} (${(body.length / 1024 / 1024).toFixed(2)} MB)`);
  } finally {
    await context.close();
  }
}

main().catch((err) => {
  console.error(err.message || err);
  process.exit(1);
});
