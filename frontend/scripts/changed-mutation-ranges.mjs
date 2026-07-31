#!/usr/bin/env node
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

export function isMutableSourceFile(file) {
  if (!file) return false;
  if (!file.startsWith("src/")) return false;
  if (!/\.(?:[cm]?[jt]s|[jt]sx)$/u.test(file)) return false;
  if (/(^|\/)__tests__\//u.test(file)) return false;
  return !/(^|\/)[^/]+\.(?:test|spec)\.[cm]?[jt]sx?$/u.test(file);
}

export function changedFilesFromContent(content) {
  return content.split(/\r?\n/u).map((line) => line.trim()).filter(isMutableSourceFile);
}

export function diffArguments(files, env = process.env) {
  if (env.GITHUB_BASE_REF) {
    return ["diff", "--relative", `origin/${env.GITHUB_BASE_REF}...HEAD`, "--", ...files];
  }
  if (env.GITHUB_EVENT_NAME === "push") {
    return ["diff", "--relative", "HEAD^", "HEAD", "--", ...files];
  }
  return ["diff", "--relative", "HEAD", "--", ...files];
}

export function mutationRangesFromDiff(diff) {
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

  return [...rangesByFile.entries()].flatMap(([file, ranges]) =>
    ranges.map(({ start, end }) => `${file}:${start}-${end}`)
  );
}

export function main(argv = process.argv, env = process.env) {
  const changedFilesPath = argv[2];
  if (!changedFilesPath) {
    throw new Error("Usage: changed-mutation-ranges.mjs <changed-files.txt>");
  }

  const changedFiles = changedFilesFromContent(readFileSync(changedFilesPath, "utf8"));

  if (changedFiles.length === 0) {
    return 0;
  }

  const diff = execFileSync("git", diffArguments(changedFiles, env), { encoding: "utf8" });
  process.stdout.write(mutationRangesFromDiff(diff).join(","));
  return 0;
}

if (fileURLToPath(import.meta.url) === process.argv[1]) {
  process.exitCode = main();
}
