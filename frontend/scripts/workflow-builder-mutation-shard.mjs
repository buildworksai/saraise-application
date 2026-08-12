#!/usr/bin/env node
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

export const WORKFLOW_BUILDER_SOURCE =
  "src/modules/workflow_automation/components/WorkflowBuilder.tsx";
export const WORKFLOW_BUILDER_TEST =
  "src/modules/workflow_automation/components/WorkflowBuilder.test.tsx";
export const DEFAULT_SHARD_COUNT = 8;
export const DEFAULT_CONCURRENCY = 2;
export const LOCAL_STORAGE_NODE_OPTION = "--localstorage-file=/tmp/saraise-frontend-localstorage.json";

export function countLines(content) {
  if (content.length === 0) return 0;
  return content.endsWith("\n")
    ? content.slice(0, -1).split(/\r?\n/u).length
    : content.split(/\r?\n/u).length;
}

export function positiveInteger(value, name) {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 1) {
    throw new Error(`${name} must be a positive integer.`);
  }
  return parsed;
}

export function shardLineRange(totalLines, shard, shardCount) {
  if (!Number.isInteger(totalLines) || totalLines < 1) {
    throw new Error("totalLines must be a positive integer.");
  }
  if (shard > shardCount) {
    throw new Error("shard must be less than or equal to shards.");
  }
  const shardSize = Math.ceil(totalLines / shardCount);
  const start = (shard - 1) * shardSize + 1;
  const end = Math.min(totalLines, shard * shardSize);
  return { start, end };
}

export function mutationTargetForShard(source, totalLines, shard, shardCount) {
  const { start, end } = shardLineRange(totalLines, shard, shardCount);
  return `${source}:${start}-${end}`;
}

export function parseArguments(argv = process.argv) {
  const options = {
    shard: 1,
    shards: DEFAULT_SHARD_COUNT,
    concurrency: DEFAULT_CONCURRENCY,
    dryRunOnly: false,
  };
  for (let index = 2; index < argv.length; index += 1) {
    const current = argv[index];
    const next = argv[index + 1];
    if (current === "--shard") {
      options.shard = positiveInteger(next, "--shard");
      index += 1;
    } else if (current === "--shards") {
      options.shards = positiveInteger(next, "--shards");
      index += 1;
    } else if (current === "--concurrency") {
      options.concurrency = positiveInteger(next, "--concurrency");
      index += 1;
    } else if (current === "--dry-run") {
      options.dryRunOnly = true;
    } else {
      throw new Error(
        "Usage: workflow-builder-mutation-shard.mjs [--shard N] [--shards N] [--concurrency N] [--dry-run]"
      );
    }
  }
  if (options.shard > options.shards) {
    throw new Error("--shard must be less than or equal to --shards.");
  }
  return options;
}

export function buildStrykerArgs({ mutationTarget, testFile, concurrency, dryRunOnly }) {
  const args = [
    "stryker",
    "run",
    "stryker.conf.json",
    "--mutate",
    mutationTarget,
    "--testFiles",
    testFile,
    "--concurrency",
    String(concurrency),
  ];
  if (dryRunOnly) args.push("--dryRunOnly");
  return args;
}

export function nodeOptionsWithLocalStorage(existing = "") {
  const options = existing.split(/\s+/u).filter(Boolean);
  if (!options.includes(LOCAL_STORAGE_NODE_OPTION)) options.push(LOCAL_STORAGE_NODE_OPTION);
  return options.join(" ");
}

export function main(argv = process.argv, env = process.env) {
  const options = parseArguments(argv);
  const totalLines = countLines(readFileSync(WORKFLOW_BUILDER_SOURCE, "utf8"));
  const mutationTarget = mutationTargetForShard(
    WORKFLOW_BUILDER_SOURCE,
    totalLines,
    options.shard,
    options.shards
  );
  const args = buildStrykerArgs({
    mutationTarget,
    testFile: WORKFLOW_BUILDER_TEST,
    concurrency: options.concurrency,
    dryRunOnly: options.dryRunOnly,
  });
  process.stdout.write(
    `WorkflowBuilder mutation shard ${options.shard}/${options.shards}: ${mutationTarget}\n`
  );
  const result = spawnSync("npx", args, {
    cwd: process.cwd(),
    env: { ...env, NODE_OPTIONS: nodeOptionsWithLocalStorage(env.NODE_OPTIONS) },
    stdio: "inherit",
  });
  return result.status ?? 1;
}

if (fileURLToPath(import.meta.url) === process.argv[1]) {
  process.exitCode = main();
}
