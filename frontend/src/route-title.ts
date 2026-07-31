export function formatRouteTitle(title: string) {
  return title.endsWith("· SARAISE") ? title : `${title} · SARAISE`;
}
