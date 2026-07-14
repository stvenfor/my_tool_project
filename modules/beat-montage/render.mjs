#!/usr/bin/env node
import { copyFileSync, existsSync, mkdirSync, readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "../..");
const BEAT_ROOT = resolve(__dirname);
const REMOTION_DIR = resolve(__dirname, "remotion");
const PUBLIC_DIR = resolve(REMOTION_DIR, "public");

function parseArgs(argv) {
  const args = { montage: "", output: "" };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--montage") args.montage = argv[++i];
    else if (arg === "--output") args.output = argv[++i];
  }
  return args;
}

function copyTree(srcDir, destDir) {
  if (!existsSync(srcDir)) return;
  mkdirSync(destDir, { recursive: true });
  for (const entry of readdirSync(srcDir)) {
    const srcPath = join(srcDir, entry);
    const destPath = join(destDir, entry);
    if (statSync(srcPath).isDirectory()) {
      copyTree(srcPath, destPath);
    } else {
      copyFileSync(srcPath, destPath);
    }
  }
}

function copyReferencedAssets(montage, publicDir) {
  mkdirSync(resolve(publicDir, "clips"), { recursive: true });
  mkdirSync(resolve(publicDir, "bgm"), { recursive: true });

  for (const cut of montage.cuts ?? []) {
    const clipPath = resolve(BEAT_ROOT, cut.clip);
    if (!existsSync(clipPath)) {
      console.warn(`Clip missing, skipped: ${clipPath}`);
      continue;
    }
    const rel = cut.clip.replace(/^clips\//, "clips/");
    const dest = resolve(publicDir, rel);
    mkdirSync(dirname(dest), { recursive: true });
    copyFileSync(clipPath, dest);
  }

  const audioPath = resolve(BEAT_ROOT, montage.audio);
  if (existsSync(audioPath)) {
    const audioName = montage.audio.replace(/^bgm\//, "");
    copyFileSync(audioPath, resolve(publicDir, "bgm", audioName));
    montage = {
      ...montage,
      audio: `bgm/${audioName}`,
    };
  } else {
    console.warn(`Audio missing: ${audioPath}`);
  }

  return montage;
}

const { montage: montageArg, output } = parseArgs(process.argv.slice(2));

if (!montageArg || !output) {
  console.error("Usage: node render.mjs --montage <montage.json> --output <mp4>");
  process.exit(1);
}

const montagePath = resolve(ROOT, montageArg);
if (!existsSync(montagePath)) {
  console.error(`Montage JSON not found: ${montagePath}`);
  process.exit(1);
}

const outputPath = resolve(ROOT, output);
let montage = JSON.parse(readFileSync(montagePath, "utf-8"));

mkdirSync(PUBLIC_DIR, { recursive: true });
mkdirSync(dirname(outputPath), { recursive: true });

copyTree(resolve(BEAT_ROOT, "clips"), resolve(PUBLIC_DIR, "clips"));
copyTree(resolve(BEAT_ROOT, "bgm"), resolve(PUBLIC_DIR, "bgm"));
montage = copyReferencedAssets(montage, PUBLIC_DIR);

const render = spawnSync(
  "npx",
  [
    "remotion",
    "render",
    "src/index.ts",
    "BeatMontageVideo",
    outputPath,
    "--props",
    JSON.stringify({ montage }),
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
