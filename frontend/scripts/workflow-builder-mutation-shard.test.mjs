import { describe, expect, it } from "vitest";
import {
  buildStrykerArgs,
  countLines,
  DEFAULT_CONCURRENCY,
  DEFAULT_SHARD_COUNT,
  LOCAL_STORAGE_NODE_OPTION,
  mutationTargetForShard,
  nodeOptionsWithLocalStorage,
  parseArguments,
  positiveInteger,
  shardLineRange,
  WORKFLOW_BUILDER_SOURCE,
  WORKFLOW_BUILDER_TEST,
} from "./workflow-builder-mutation-shard.mjs";

describe("WorkflowBuilder mutation shard runner", () => {
  it("counts source lines without inventing a trailing blank line", () => {
    expect(countLines("")).toBe(0);
    expect(countLines("one")).toBe(1);
    expect(countLines("one\ntwo")).toBe(2);
    expect(countLines("one\ntwo\n")).toBe(2);
  });

  it("computes deterministic one-based shard ranges", () => {
    expect(shardLineRange(100, 1, 4)).toEqual({ start: 1, end: 25 });
    expect(shardLineRange(100, 2, 4)).toEqual({ start: 26, end: 50 });
    expect(shardLineRange(101, 4, 4)).toEqual({ start: 79, end: 101 });
    expect(mutationTargetForShard("src/file.tsx", 101, 4, 4)).toBe("src/file.tsx:79-101");
  });

  it("rejects invalid shard values before invoking Stryker", () => {
    expect(() => positiveInteger("0", "--shard")).toThrow("--shard must be a positive integer.");
    expect(() => shardLineRange(10, 3, 2)).toThrow("shard must be less than or equal to shards.");
    expect(() => shardLineRange(0, 1, 2)).toThrow("totalLines must be a positive integer.");
    expect(() => parseArguments(["node", "script", "--shard", "9", "--shards", "8"])).toThrow(
      "--shard must be less than or equal to --shards."
    );
    expect(() => parseArguments(["node", "script", "--unknown"])).toThrow(
      "Usage: workflow-builder-mutation-shard.mjs"
    );
  });

  it("parses defaults and explicit CLI options", () => {
    expect(parseArguments(["node", "script"])).toEqual({
      shard: 1,
      shards: DEFAULT_SHARD_COUNT,
      concurrency: DEFAULT_CONCURRENCY,
      dryRunOnly: false,
    });
    expect(
      parseArguments([
        "node",
        "script",
        "--shard",
        "3",
        "--shards",
        "12",
        "--concurrency",
        "4",
        "--dry-run",
      ])
    ).toEqual({ shard: 3, shards: 12, concurrency: 4, dryRunOnly: true });
  });

  it("builds a focused Stryker command using the WorkflowBuilder test file", () => {
    expect(
      buildStrykerArgs({
        mutationTarget: `${WORKFLOW_BUILDER_SOURCE}:1-100`,
        testFile: WORKFLOW_BUILDER_TEST,
        concurrency: 2,
        dryRunOnly: true,
      })
    ).toEqual([
      "stryker",
      "run",
      "stryker.conf.json",
      "--mutate",
      `${WORKFLOW_BUILDER_SOURCE}:1-100`,
      "--testFiles",
      WORKFLOW_BUILDER_TEST,
      "--concurrency",
      "2",
      "--dryRunOnly",
    ]);
  });

  it("adds the Node localStorage option idempotently", () => {
    expect(nodeOptionsWithLocalStorage("")).toBe(LOCAL_STORAGE_NODE_OPTION);
    expect(nodeOptionsWithLocalStorage("--trace-warnings")).toBe(
      `--trace-warnings ${LOCAL_STORAGE_NODE_OPTION}`
    );
    expect(nodeOptionsWithLocalStorage(LOCAL_STORAGE_NODE_OPTION)).toBe(LOCAL_STORAGE_NODE_OPTION);
  });
});
