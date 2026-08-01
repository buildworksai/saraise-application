export function formatRouteTitle(title: string | undefined, fallback = "SARAISE") {
  const trimmedTitle = title?.trim();
  const resolvedTitle = trimmedTitle === undefined || trimmedTitle === "" ? fallback : trimmedTitle;
  return resolvedTitle.endsWith("· SARAISE") ? resolvedTitle : `${resolvedTitle} · SARAISE`;
}
