import { execFileSync } from "node:child_process";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const NON_APPLICABLE_RSC_ADVISORY = 1124282;
const SOURCE_ROOT = new URL("../src/", import.meta.url).pathname;
const RSC_PATTERNS = [
  "RSCHydratedRouter",
  "RSCStaticRouter",
  "createCallServer",
  "getRSCStream",
  "matchRSCServerRequest",
  "react-server",
  "react-router/rsc",
  "react-router/dom/server",
  "unstable_RSC",
];

function readAudit() {
  try {
    execFileSync("npm", ["audit", "--audit-level", "moderate", "--json"], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    });
    return { vulnerabilities: {} };
  } catch (error) {
    const output = String(error.stdout ?? "");
    if (!output.trim()) {
      throw error;
    }
    return JSON.parse(output);
  }
}

function sourceFiles(dir) {
  const files = [];
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    const stat = statSync(path);
    if (stat.isDirectory()) {
      files.push(...sourceFiles(path));
    } else if (/\.(ts|tsx|js|jsx|mjs|cjs)$/.test(entry)) {
      files.push(path);
    }
  }
  return files;
}

function findRscUsage() {
  const matches = [];
  for (const file of sourceFiles(SOURCE_ROOT)) {
    const content = readFileSync(file, "utf8");
    for (const pattern of RSC_PATTERNS) {
      if (content.includes(pattern)) {
        matches.push(`${relative(process.cwd(), file)}:${pattern}`);
      }
    }
  }
  return matches;
}

function advisoryIds(via) {
  return via
    .filter((item) => typeof item === "object" && item !== null)
    .map((item) => item.source);
}

const audit = readAudit();
const vulnerabilityMap = audit.vulnerabilities ?? {};
const vulnerabilities = Object.values(vulnerabilityMap);
const unresolved = [];

function hasOnlyRscAdvisory(vulnerability) {
  const ids = advisoryIds(vulnerability.via ?? []);
  return ids.length === 1 && ids[0] === NON_APPLICABLE_RSC_ADVISORY;
}

for (const vulnerability of vulnerabilities) {
  const onlyRscAdvisory =
    vulnerability.name === "react-router" && hasOnlyRscAdvisory(vulnerability);
  const onlyViaAllowedReactRouter =
    vulnerability.name === "react-router-dom" &&
    Array.isArray(vulnerability.via) &&
    vulnerability.via.length === 1 &&
    vulnerability.via[0] === "react-router" &&
    hasOnlyRscAdvisory(vulnerabilityMap["react-router"]);

  if (!onlyRscAdvisory && !onlyViaAllowedReactRouter) {
    unresolved.push(vulnerability);
  }
}

const rscUsage = findRscUsage();
if (rscUsage.length > 0) {
  console.error("React Router RSC APIs detected; GHSA-qwww-vcr4-c8h2 is applicable.");
  for (const match of rscUsage) {
    console.error(`- ${match}`);
  }
  process.exit(1);
}

if (unresolved.length > 0) {
  console.error("Unresolved npm audit vulnerabilities:");
  for (const vulnerability of unresolved) {
    console.error(`- ${vulnerability.name}: ${vulnerability.severity}`);
  }
  process.exit(1);
}

console.log("npm security audit passed.");
if (vulnerabilities.length > 0) {
  console.log(
    "GHSA-qwww-vcr4-c8h2 is not applicable: this BrowserRouter SPA has no React Router unstable RSC API usage."
  );
}
