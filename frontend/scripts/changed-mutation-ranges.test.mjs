import { describe, expect, it } from "vitest";
import {
  changedFilesFromContent,
  diffArguments,
  isMutableSourceFile,
  mutationRangesFromDiff,
} from "./changed-mutation-ranges.mjs";

describe("changed mutation ranges", () => {
  it("keeps only mutable source files from the changed-file list", () => {
    expect(
      changedFilesFromContent(`
        src/App.tsx
        src/modules/crm/routes.ts
        src/modules/crm/__tests__/routes.test.ts
        src/modules/dms/routes.spec.ts
        scripts/changed-mutation-ranges.mjs
        vite.config.ts
      `)
    ).toEqual(["src/App.tsx", "src/modules/crm/routes.ts"]);

    expect(isMutableSourceFile("")).toBe(false);
    expect(isMutableSourceFile("src/modules/crm/routes.cts")).toBe(true);
    expect(isMutableSourceFile("src/modules/crm/routes.mtsx")).toBe(false);
  });

  it("selects the correct git diff comparison for pull requests, pushes, and local edits", () => {
    expect(diffArguments(["src/App.tsx"], { GITHUB_BASE_REF: "main" })).toEqual([
      "diff",
      "--relative",
      "origin/main...HEAD",
      "--",
      "src/App.tsx",
    ]);

    expect(diffArguments(["src/App.tsx"], { GITHUB_EVENT_NAME: "push" })).toEqual([
      "diff",
      "--relative",
      "HEAD^",
      "HEAD",
      "--",
      "src/App.tsx",
    ]);

    expect(diffArguments(["src/App.tsx"], {})).toEqual([
      "diff",
      "--relative",
      "HEAD",
      "--",
      "src/App.tsx",
    ]);
  });

  it("returns contiguous added-line ranges from unified git diff output", () => {
    const diff = `diff --git a/src/a.ts b/src/a.ts
--- a/src/a.ts
+++ b/src/a.ts
@@ -10,4 +10,5 @@
 existing
+added one
+added two
 unchanged
-removed
+replacement
diff --git a/src/b.ts b/src/b.ts
--- a/src/b.ts
+++ b/src/b.ts
@@ -1,2 +20,3 @@
 context
+other file
`;

    expect(mutationRangesFromDiff(diff)).toEqual(["src/a.ts:11-12", "src/a.ts:14-14", "src/b.ts:21-21"]);
  });
});
