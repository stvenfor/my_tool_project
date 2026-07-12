#!/usr/bin/env node
import { copyFileSync, existsSync, mkdirSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "../..");
const REMOTION_DIR = resolve(__dirname, "remotion");
const PUBLIC_DIR = resolve(REMOTION_DIR, "public");

function parseArgs(argv) {
  const args = { storyboard: "", workDir: "", output: "" };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--storyboard") args.storyboard = argv[++i];
    else if (arg === "--work-dir") args.workDir = argv[++i];
    else if (arg === "--output") args.output = argv[++i];
  }
  return args;
}

function copyIfExists(src, dest) {
  if (!existsSync(src)) return false;
  mkdirSync(dirname(dest), { recursive: true });
  copyFileSync(src, dest);
  return true;
}

const { storyboard: storyboardArg, workDir: workDirArg, output } = parseArgs(process.argv.slice(2));

if (!storyboardArg || !workDirArg || !output) {
  console.error(
    "Usage: node render.mjs --storyboard <storyboard.json> --work-dir <work-dir> --output <mp4>",
  );
  process.exit(1);
}

const storyboardPath = resolve(ROOT, storyboardArg);
const workDir = resolve(ROOT, workDirArg);
const outputPath = resolve(ROOT, output);

if (!existsSync(storyboardPath)) {
  console.error(`Storyboard JSON not found: ${storyboardPath}`);
  process.exit(1);
}

const storyboard = JSON.parse(readFileSync(storyboardPath, "utf-8"));

mkdirSync(PUBLIC_DIR, { recursive: true });
mkdirSync(dirname(outputPath), { recursive: true });

for (const shot of storyboard.shots ?? []) {
  const clipPath = resolve(workDir, shot.clip);
  const destPath = resolve(PUBLIC_DIR, shot.clip);
  if (!copyIfExists(clipPath, destPath)) {
    console.warn(`Clip missing, skipped: ${clipPath}`);
  }
}

if (storyboard.narration) {
  copyIfExists(resolve(workDir, storyboard.narration), resolve(PUBLIC_DIR, storyboard.narration));
}

if (storyboard.bgm) {
  copyIfExists(resolve(workDir, storyboard.bgm), resolve(PUBLIC_DIR, storyboard.bgm));
}

const render = spawnSync(
  "npx",
  [
    "remotion",
    "render",
    "src/index.ts",
    "ThreeKingdomsEnglishVideo",
    outputPath,
    "--props",
    JSON.stringify({ storyboard }),
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
