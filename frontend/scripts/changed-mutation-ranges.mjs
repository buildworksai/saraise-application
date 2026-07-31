#!/usr/bin/env node
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";

const changedFilesPath = process.argv[2];
if (!changedFilesPath) {
  throw new Error("Usage: changed-mutation-ranges.mjs <changed-files.txt>");
}

const changedFiles = readFileSync(changedFilesPath, "utf8")
  .split(/\r?\n/u)
  .map((line) => line.trim())
  .filter(Boolean);

if (changedFiles.length === 0) {
  process.exit(0);
}

function diffArguments(files) {
  if (process.env.GITHUB_BASE_REF) {
    return ["diff", "--relative", `origin/${process.env.GITHUB_BASE_REF}...HEAD`, "--", ...files];
  }
  if (process.env.GITHUB_EVENT_NAME === "push") {
    return ["diff", "--relative", "HEAD^", "HEAD", "--", ...files];
  }
  return ["diff", "--relative", "HEAD", "--", ...files];
}

const diff = execFileSync("git", diffArguments(changedFiles), { encoding: "utf8" });
const rangesByFile = new Map();
let currentFile;
let newLine = 0;

for (const line of diff.split(/\r?\n/u)) {
  if (line.startsWith("+++ b/")) {
    currentFile = line.slice("+++ b/".length);
    if (!rangesByFile.has(currentFile)) rangesByFile.set(currentFile, []);
    continue;
  }

  const hunk = /^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@/u.exec(line);
  if (hunk) {
    newLine = Number(hunk[1]);
    continue;
  }

  if (!currentFile || line.startsWith("diff --git ") || line.startsWith("--- ")) continue;

  if (line.startsWith("+")) {
    const ranges = rangesByFile.get(currentFile);
    const previous = ranges.at(-1);
    if (previous && previous.end + 1 === newLine) {
      previous.end = newLine;
    } else {
      ranges.push({ start: newLine, end: newLine });
    }
    newLine += 1;
  } else if (!line.startsWith("-")) {
    newLine += 1;
  }
}

const mutateRanges = [...rangesByFile.entries()].flatMap(([file, ranges]) =>
  ranges.map(({ start, end }) => `${file}:${start}-${end}`)
);

process.stdout.write(mutateRanges.join(","));
