#!/usr/bin/env node
/** Validate douyin-video.json without launching browser. */
import fs from "node:fs";
import path from "node:path";

const input = process.argv[2];
if (!input) {
  console.error("Usage: node validate-douyin.mjs <douyin-video.json>");
  process.exit(1);
}

const file = path.resolve(input);
const parsed = JSON.parse(fs.readFileSync(file, "utf8"));
if (!parsed.videoPath) throw new Error("videoPath is required");
const video = path.resolve(path.dirname(file), parsed.videoPath);
if (!fs.existsSync(video)) throw new Error(`Video not found: ${video}`);
if (!parsed.title) throw new Error("title is required");

console.log(
  JSON.stringify(
    {
      ok: true,
      title: parsed.title,
      videoPath: video,
      size_mb: (fs.statSync(video).size / 1024 / 1024).toFixed(2),
      tags: parsed.tags ?? [],
    },
    null,
    2,
  ),
);
