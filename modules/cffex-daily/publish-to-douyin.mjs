#!/usr/bin/env node
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "../..");
const OUTPUT_DIR = resolve(__dirname, "work/output");
const PUBLISH_SCRIPT = resolve(__dirname, "../shared/douyin/publish-video.mjs");

function parseArgs(argv) {
  const args = { date: "", passthrough: [] };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--date") {
      args.date = argv[++i] ?? "";
      continue;
    }
    args.passthrough.push(arg);
  }
  return args;
}

function resolveConfigPath(date) {
  if (date) {
    return resolve(OUTPUT_DIR, `citic-net-positions-${date}-douyin.json`);
  }
  return resolve(OUTPUT_DIR, "douyin-video.json");
}

const args = parseArgs(process.argv.slice(2));
const configPath = resolveConfigPath(args.date);

if (!existsSync(configPath)) {
  console.error(`Douyin config not found: ${configPath}`);
  console.error("Run npm run cffex:daily first, or pass --date YYYYMMDD.");
  process.exit(1);
}

const hasSkipMusic = args.passthrough.includes("--skip-music");
const publishArgs = [
  PUBLISH_SCRIPT,
  configPath,
  ...args.passthrough,
  ...(hasSkipMusic ? [] : ["--skip-music"]),
];

const result = spawnSync("node", publishArgs, {
  cwd: ROOT,
  stdio: "inherit",
  env: process.env,
});

process.exit(result.status ?? 1);
