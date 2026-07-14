#!/usr/bin/env node
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "../..");
const PUBLISH_SCRIPT = resolve(__dirname, "../shared/douyin/publish-video.mjs");

function parseArgs(argv) {
  const args = { config: "", passthrough: [] };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--config") {
      args.config = argv[++i] ?? "";
      continue;
    }
    args.passthrough.push(arg);
  }
  return args;
}

const args = parseArgs(process.argv.slice(2));
const configPath = args.config
  ? resolve(ROOT, args.config)
  : resolve(ROOT, "modules/viral-english-dub/work/demo-clip/douyin-video.json");

if (!existsSync(configPath)) {
  console.error(`Douyin config not found: ${configPath}`);
  console.error("Run npm run viral-dub:pipeline first, or pass --config <path>.");
  process.exit(1);
}

const hasSkipMusic = args.passthrough.includes("--skip-music");
const publishArgs = [
  PUBLISH_SCRIPT,
  configPath,
  ...args.passthrough,
  ...(hasSkipMusic ? [] : ["--skip-music"]),
];

const result = spawnSync("node", publishArgs, { stdio: "inherit", cwd: ROOT });
process.exit(result.status ?? 1);
