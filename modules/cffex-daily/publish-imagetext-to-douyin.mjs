#!/usr/bin/env node
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "../..");
const OUTPUT_DIR = resolve(__dirname, "work/output");
const PUBLISH_SCRIPT = resolve(
  __dirname,
  "../shared/douyin/publish-imagetext.mjs"
);

function parseArgs(argv) {
  const args = { date: "", image: "", config: "", passthrough: [] };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--date") {
      args.date = argv[++i] ?? "";
      continue;
    }
    if (arg === "--image") {
      args.image = argv[++i] ?? "";
      continue;
    }
    if (arg === "--config") {
      args.config = argv[++i] ?? "";
      continue;
    }
    args.passthrough.push(arg);
  }
  return args;
}

function buildConfig(date, imagePath) {
  const videoMetaPath = resolve(
    OUTPUT_DIR,
    `citic-net-positions-${date}-douyin.json`
  );
  let title = `${date}中信期货净持仓`;
  let description = "";
  let tags = ["期货", "股指期货", "中信期货", "持仓数据", "金融"];

  if (existsSync(videoMetaPath)) {
    const meta = JSON.parse(readFileSync(videoMetaPath, "utf8"));
    title = meta.title || title;
    description = meta.description || description;
    tags = meta.tags || tags;
  }

  const out = resolve(OUTPUT_DIR, `citic-net-positions-${date}-imagetext.json`);
  writeFileSync(
    out,
    JSON.stringify(
      {
        imagePaths: [resolve(imagePath)],
        title,
        description,
        tags,
      },
      null,
      2
    ),
    "utf8"
  );
  return out;
}

const args = parseArgs(process.argv.slice(2));
let configPath = args.config ? resolve(args.config) : "";

if (!configPath) {
  if (args.image && args.date) {
    configPath = buildConfig(args.date, args.image);
  } else if (args.date) {
    const candidate = resolve(
      OUTPUT_DIR,
      `citic-net-positions-${args.date}-imagetext.json`
    );
    if (!existsSync(candidate)) {
      console.error(`Imagtext config not found: ${candidate}`);
      console.error(
        "Pass --image <beautified.png> --date YYYYMMDD, or --config."
      );
      process.exit(1);
    }
    configPath = candidate;
  } else {
    configPath = resolve(OUTPUT_DIR, "douyin-imagetext.json");
  }
}

if (!existsSync(configPath)) {
  console.error(`Douyin imagetext config not found: ${configPath}`);
  console.error(
    "Provide --config, or --date YYYYMMDD --image /path/to/beautified.png"
  );
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
