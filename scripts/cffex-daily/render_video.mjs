#!/usr/bin/env node
import { copyFileSync, existsSync, mkdirSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "../..");
const REMOTION_DIR = resolve(__dirname, "remotion");
const PUBLIC_DIR = resolve(REMOTION_DIR, "public");
const LOGO_FILE = resolve(__dirname, "logo.png");
const BGM_FILE = resolve(__dirname, "bgm.mp3");

function parseArgs(argv) {
  const args = { json: "", output: "", image: "" };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--json") args.json = argv[++i];
    else if (arg === "--output") args.output = argv[++i];
    else if (arg === "--image") args.image = argv[++i];
  }
  return args;
}

const { json, output, image } = parseArgs(process.argv.slice(2));

if (!output) {
  console.error("Usage: node render_video.mjs --json <report.json> --output <mp4>");
  process.exit(1);
}

let reportPath = json ? resolve(ROOT, json) : "";
if (!reportPath && image) {
  const imagePath = resolve(ROOT, image);
  const guessed = imagePath.replace(/\.png$/i, ".json");
  if (existsSync(guessed)) reportPath = guessed;
}

if (!reportPath || !existsSync(reportPath)) {
  console.error(`Report JSON not found: ${reportPath || json}`);
  process.exit(1);
}

const outputPath = resolve(ROOT, output);
const report = JSON.parse(readFileSync(reportPath, "utf-8"));

mkdirSync(PUBLIC_DIR, { recursive: true });
mkdirSync(dirname(outputPath), { recursive: true });

if (existsSync(LOGO_FILE)) {
  copyFileSync(LOGO_FILE, resolve(PUBLIC_DIR, "logo.png"));
}

if (existsSync(BGM_FILE)) {
  copyFileSync(BGM_FILE, resolve(PUBLIC_DIR, "bgm.mp3"));
}

const propsFile = resolve(PUBLIC_DIR, "report-props.json");
copyFileSync(reportPath, propsFile);

const render = spawnSync(
  "npx",
  [
    "remotion",
    "render",
    "src/index.ts",
    "CiticReportVideo",
    outputPath,
    "--props",
    JSON.stringify({ report }),
    "--log=error",
  ],
  {
    cwd: REMOTION_DIR,
    stdio: "inherit",
    env: process.env,
  },
);

if (render.status !== 0) {
  process.exit(render.status ?? 1);
}

console.log(`Saved video: ${outputPath}`);
