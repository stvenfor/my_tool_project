#!/usr/bin/env node
/** Download Douyin video/audio by sniffing network for douyinvod URLs. */
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

function scoreMediaUrl(url, kind) {
  let score = url.length;
  if (url.includes("douyinvod")) score += 1000;
  if (kind === "video" && (url.includes("mime_type=video") || url.includes("/video/"))) score += 500;
  if (kind === "audio" && (url.includes("mime_type=audio") || url.includes("/audio/"))) score += 500;
  return score;
}

function pickBestUrl(urls, kind) {
  const unique = [...new Set(urls.filter(Boolean))];
  unique.sort((a, b) => scoreMediaUrl(b, kind) - scoreMediaUrl(a, kind));
  if (kind === "audio") {
    return (
      unique.find((u) => u.includes("media-audio")) ||
      unique.find((u) => u.includes("mime_type=audio") || u.includes("/audio/")) ||
      unique.find((u) => u.includes("media_audio")) ||
      ""
    );
  }
  return (
    unique.find((u) => u.includes("media-video")) ||
    unique.find((u) => u.includes("mime_type=video") || u.includes("/video/") || u.includes(".mp4")) ||
    unique[0] ||
    ""
  );
}

async function downloadBinary(context, url, outputPath) {
  const response = await context.request.get(url, {
    headers: { Referer: "https://www.douyin.com/" },
  });
  if (!response.ok()) {
    throw new Error(`Download failed: HTTP ${response.status()} for ${url.slice(0, 80)}`);
  }
  const body = await response.body();
  if (body.length < 1000) {
    throw new Error(`Download too small (${body.length} bytes)`);
  }
  fs.writeFileSync(outputPath, body);
  return body.length;
}

async function main() {
  const { url, output } = parseArgs(process.argv.slice(2));
  if (!url || !output) {
    console.error("Usage: node download_douyin_ref.mjs --url <url> --output <path.mp4>");
    process.exit(1);
  }

  const outputPath = path.resolve(output);
  const outputDir = path.dirname(outputPath);
  const outputBase = outputPath.replace(/\.[^.]+$/, "");
  fs.mkdirSync(outputDir, { recursive: true });

  const capturedVideo = [];
  const capturedAudio = [];
  const context = await chromium.launchPersistentContext(DOUYIN_PROFILE, {
    headless: true,
    channel: "chrome",
    args: ["--disable-blink-features=AutomationControlled"],
  });

  try {
    const page = context.pages()[0] ?? (await context.newPage());
    page.on("response", (response) => {
      const responseUrl = response.url();
      if (!responseUrl.includes("douyinvod") && !responseUrl.includes("douyin")) {
        return;
      }
      if (
        responseUrl.includes("media-audio") ||
        responseUrl.includes("mime_type=audio") ||
        responseUrl.includes("/audio/") ||
        responseUrl.includes("media_audio")
      ) {
        capturedAudio.push(responseUrl);
        return;
      }
      if (
        responseUrl.includes("media-video") ||
        responseUrl.includes("mime_type=video") ||
        responseUrl.includes("/video/") ||
        responseUrl.includes(".mp4")
      ) {
        capturedVideo.push(responseUrl);
      }
    });

    const directVideoId = url.match(/\/video\/(\d+)/)?.[1];
    const targetUrl = directVideoId
      ? `https://www.douyin.com/video/${directVideoId}`
      : url;

    await page.goto(targetUrl, { waitUntil: "domcontentloaded", timeout: 90000 });
    await page.waitForTimeout(3000);

    if (!page.url().includes("/video/")) {
      await page.waitForURL(/\/video\//, { timeout: 30000 }).catch(() => {});
    }

    await page.waitForSelector("video", { timeout: 30000 }).catch(() => {});
    await page.click("video").catch(() => {});
    await page.waitForTimeout(5000);

    const domSrc = await page.evaluate(() => {
      const videos = [...document.querySelectorAll("video")];
      const candidates = videos
        .flatMap((v) => [v.src, v.currentSrc])
        .filter((src) => src && (src.includes("douyinvod") || src.includes(".mp4")));
      candidates.sort((a, b) => b.length - a.length);
      return candidates[0] || "";
    });
    if (domSrc) {
      capturedVideo.push(domSrc);
    }

    const jsonUrls = await page.evaluate(() => {
      const found = [];
      const scripts = [...document.querySelectorAll("script")];
      for (const script of scripts) {
        const text = script.textContent || "";
        if (!text.includes("douyinvod") && !text.includes("playAddr")) {
          continue;
        }
        const matches = text.match(/https?:\/\/[^"'\s]+douyinvod[^"'\s]*/g) || [];
        found.push(...matches);
      }
      return found;
    });
    for (const mediaUrl of jsonUrls) {
      if (mediaUrl.includes("media-audio") || mediaUrl.includes("mime_type=audio") || mediaUrl.includes("/audio/")) {
        capturedAudio.push(mediaUrl);
      } else {
        capturedVideo.push(mediaUrl);
      }
    }

    const videoSrc = pickBestUrl(capturedVideo, "video");
    const audioSrc = pickBestUrl(capturedAudio, "audio");

    if (!videoSrc && !audioSrc) {
      throw new Error(`No media URL captured (page: ${page.url()})`);
    }

    if (videoSrc) {
      const bytes = await downloadBinary(context, videoSrc, outputPath);
      console.log(`Saved video: ${outputPath} (${(bytes / 1024 / 1024).toFixed(2)} MB)`);
    }

    if (audioSrc) {
      const audioPath = `${outputBase}.audio.m4a`;
      const bytes = await downloadBinary(context, audioSrc, audioPath);
      console.log(`Saved audio: ${audioPath} (${(bytes / 1024 / 1024).toFixed(2)} MB)`);
    } else {
      console.log("No separate audio URL captured.");
    }
  } finally {
    await context.close();
  }
}

main().catch((err) => {
  console.error(err.message || err);
  process.exit(1);
});
