import type {
  TenantApplicationMode,
  TenantRoute,
  TenantRouteIcon,
  TenantRouteModule,
} from "./tenant-route-types";

/** A navigable leaf. `routeId` always resolves to an entry in `tenantRoutes`. */
export interface TenantSidebarLeaf {
  id: string;
  routeId: string;
  module: string;
  path: string;
  label: string;
  icon: TenantRouteIcon;
  order: number;
}

/** Module branch consumed by the tenant sidebar migration shim. */
export interface TenantSidebarBranch {
  id: string;
  module: string;
  label: string;
  icon: TenantRouteIcon;
  order: number;
  children: readonly TenantSidebarLeaf[];
}

/** A single registry violation with enough ownership context to fix it. */
export interface TenantRouteValidationIssue {
  routeId: string;
  sourceFile: string;
  message: string;
}

export class TenantRouteRegistryError extends Error {
  readonly issues: readonly TenantRouteValidationIssue[];

  constructor(issues: readonly TenantRouteValidationIssue[]) {
    super(
      `Tenant route registry validation failed:\n${issues
        .map((issue) => `- ${issue.sourceFile} [${issue.routeId}]: ${issue.message}`)
        .join("\n")}`,
    );
    this.name = "TenantRouteRegistryError";
    this.issues = issues;
  }
}

const routeModules = import.meta.glob<TenantRouteModule>(
  "../modules/*/routes.ts",
  { eager: true },
);

const KNOWN_ACRONYMS = new Map<string, string>([["crm", "CRM"]]);

function normalizePath(path: string): string {
  return path.length > 1 ? path.replace(/\/+$/, "") : path;
}

function hasRouteParameter(path: string): boolean {
  return path
    .split("/")
    .some((segment) => segment.startsWith(":") || segment === "*");
}

function formatModuleLabel(moduleName: string): string {
  return moduleName
    .split(/[_-]/u)
    .map(
      (word) =>
        KNOWN_ACRONYMS.get(word.toLowerCase()) ??
        `${word.charAt(0).toUpperCase()}${word.slice(1)}`,
    )
    .join(" ");
}

function getRoutesFromModule(
  modulePath: string,
  routeModule: TenantRouteModule,
): readonly TenantRoute[] {
  const routes = routeModule.tenantRoutes ?? routeModule.default;
  if (!routes) {
    throw new Error(
      `${modulePath} must export a tenantRoutes array or a default TenantRoute array.`,
    );
  }
  return routes;
}

function aggregateTenantRoutes(): readonly TenantRoute[] {
  return Object.entries(routeModules)
    .sort(([leftPath], [rightPath]) => leftPath.localeCompare(rightPath))
    .flatMap(([modulePath, routeModule]) =>
      getRoutesFromModule(modulePath, routeModule),
    );
}

function addIssue(
  issues: TenantRouteValidationIssue[],
  route: TenantRoute,
  message: string,
): void {
  issues.push({
    routeId: route.id || "<missing-id>",
    sourceFile: route.sourceFile || "<missing-source>",
    message,
  });
}

function validateRequiredFields(
  route: TenantRoute,
  issues: TenantRouteValidationIssue[],
): void {
  if (!route.id.trim()) addIssue(issues, route, "id must not be empty");
  if (!route.module.trim()) addIssue(issues, route, "module must not be empty");
  if (!route.sourceFile.trim()) {
    addIssue(issues, route, "sourceFile must not be empty");
  }
  if (route.module === "document_intelligence" && !route.title?.trim()) {
    addIssue(issues, route, "title must not be empty");
  }
  if (!route.path.startsWith("/")) {
    addIssue(issues, route, "path must be absolute");
  }
}

function validateSidebarRoute(
  route: TenantRoute,
  issues: TenantRouteValidationIssue[],
): void {
  if (route.navigation.type !== "sidebar") return;
  if (!route.navigation.label.trim()) {
    addIssue(issues, route, "sidebar label must not be empty");
  }
  if (!Number.isFinite(route.navigation.order)) {
    addIssue(issues, route, "sidebar order must be finite");
  }
  const navigationPath = route.navigation.path ?? route.path;
  if (!navigationPath.startsWith("/")) {
    addIssue(issues, route, "sidebar navigation path must be absolute");
  }
  if (hasRouteParameter(navigationPath)) {
    addIssue(issues, route, "sidebar paths cannot contain route parameters");
  }
}

/** Return every structural violation without hiding later failures behind the first. */
export function getTenantRouteValidationIssues(
  routes: readonly TenantRoute[],
): readonly TenantRouteValidationIssue[] {
  const issues: TenantRouteValidationIssue[] = [];
  const routesById = new Map<string, TenantRoute>();
  const routesByPath = new Map<string, TenantRoute>();

  for (const route of routes) {
    validateRequiredFields(route, issues);

    const existingId = routesById.get(route.id);
    if (existingId) {
      addIssue(issues, route, `duplicate id also declared by ${existingId.sourceFile}`);
    } else {
      routesById.set(route.id, route);
    }

    const normalizedPath = normalizePath(route.path);
    const existingPath = routesByPath.get(normalizedPath);
    if (existingPath) {
      addIssue(
        issues,
        route,
        `duplicate path also declared by ${existingPath.sourceFile} [${existingPath.id}]`,
      );
    } else {
      routesByPath.set(normalizedPath, route);
    }

    validateSidebarRoute(route, issues);
  }

  for (const route of routes) {
    if (route.navigation.type !== "contextual") continue;
    const parent = routesById.get(route.navigation.parentRouteId);
    if (!parent) {
      addIssue(
        issues,
        route,
        `contextual parent ${route.navigation.parentRouteId} does not exist`,
      );
    } else if (parent.navigation.type !== "sidebar") {
      addIssue(issues, route, "contextual parent must be a sidebar route");
    } else if (parent.module !== route.module) {
      addIssue(issues, route, "contextual parent must belong to the same module");
    }
    if (route.module === "document_intelligence") {
      if (!route.navigation.label?.trim()) addIssue(issues, route, "contextual NavItem label must not be empty");
      if (!route.navigation.icon) addIssue(issues, route, "contextual NavItem icon is required");
      if (!Number.isFinite(route.navigation.order)) addIssue(issues, route, "contextual NavItem order must be finite");
    }
  }

  return issues;
}

/** Stop application startup when a discovered module publishes invalid routes. */
export function validateTenantRoutes(routes: readonly TenantRoute[]): void {
  const issues = getTenantRouteValidationIssues(routes);
  if (issues.length > 0) throw new TenantRouteRegistryError(issues);
}

/** Ensure derived sidebar leaves still resolve after future tree transformations. */
export function validateTenantSidebarTree(
  routes: readonly TenantRoute[],
  tree: readonly TenantSidebarBranch[],
): void {
  const routesById = new Map(routes.map((route) => [route.id, route]));

  for (const branch of tree) {
    for (const leaf of branch.children) {
      const route = routesById.get(leaf.routeId);
      if (!route) {
        throw new Error(`Sidebar leaf ${leaf.id} does not resolve to a tenant route.`);
      }
      const expectedPath = route.navigation.type === "sidebar"
        ? route.navigation.path ?? route.path
        : (hasRouteParameter(route.path)
          ? routesById.get(route.navigation.parentRouteId)?.path
          : route.path);
      if (expectedPath !== leaf.path) {
        throw new Error(`Sidebar leaf ${leaf.id} does not match its tenant route.`);
      }
      if (hasRouteParameter(leaf.path)) {
        throw new Error(`Sidebar leaf ${leaf.id} contains a route parameter.`);
      }
    }
  }
}

/** Build stable, module-grouped sidebar branches from validated route descriptors. */
export function buildTenantSidebarTree(
  routes: readonly TenantRoute[],
  grantedPermissions?: ReadonlySet<string>,
): readonly TenantSidebarBranch[] {
  validateTenantRoutes(routes);
  const leavesByModule = new Map<string, TenantSidebarLeaf[]>();

  const routesById = new Map(routes.map((route) => [route.id, route]));
  for (const route of routes) {
    const contextualNavItem = ["process_mining", "integration_platform"].includes(route.module) && route.navigation.type === "contextual";
    if (route.navigation.type !== "sidebar" && !contextualNavItem) continue;
    if (grantedPermissions && route.requiredPermission && !grantedPermissions.has(route.requiredPermission)) continue;
    const parent = route.navigation.type === "contextual" ? routesById.get(route.navigation.parentRouteId) : undefined;
    const parentNavigation = parent?.navigation.type === "sidebar" ? parent.navigation : undefined;
    const derivedLabel = route.sourceFile.split('/').at(-1)?.replace(/Page\.tsx$/, '').replace(/([a-z])([A-Z])/g, '$1 $2') ?? route.id;
    const leaves = leavesByModule.get(route.module) ?? [];
    leaves.push({
      id: route.id,
      routeId: route.id,
      module: route.module,
      path: route.navigation.type === "sidebar" ? route.navigation.path ?? route.path : (hasRouteParameter(route.path) ? parent?.path ?? route.path : route.path),
      label: route.navigation.type === "sidebar" ? route.navigation.label : route.navigation.label ?? derivedLabel,
      icon: route.navigation.type === "sidebar" ? route.navigation.icon : route.navigation.icon ?? parentNavigation!.icon,
      order: route.navigation.type === "sidebar" ? route.navigation.order : route.navigation.order ?? (parentNavigation?.order ?? 0) + (leaves.length + 1) / 100,
    });
    leavesByModule.set(route.module, leaves);
  }

  const tree = Array.from(leavesByModule.entries())
    .map(([module, leaves]) => {
      const sortedLeaves = leaves.sort(
        (left, right) => left.order - right.order || left.label.localeCompare(right.label),
      );
      const firstLeaf = sortedLeaves[0];
      if (!firstLeaf) throw new Error(`Sidebar module ${module} has no routes.`);
      return {
        id: `module:${module}`,
        module,
        label: formatModuleLabel(module),
        icon: firstLeaf.icon,
        order: firstLeaf.order,
        children: sortedLeaves,
      };
    })
    .sort((left, right) => left.order - right.order || left.label.localeCompare(right.label));

  validateTenantSidebarTree(routes, tree);
  return tree;
}

/** Filter descriptors for the configured runtime while retaining all routes by default. */
export function getTenantRoutesForMode(
  routes: readonly TenantRoute[],
  mode?: TenantApplicationMode,
): readonly TenantRoute[] {
  if (!mode) return routes;
  return routes.filter((route) => !route.modes || route.modes.includes(mode));
}

export const tenantRoutes = aggregateTenantRoutes();
validateTenantRoutes(tenantRoutes);

export const tenantSidebarTree = buildTenantSidebarTree(tenantRoutes);

export function getTenantSidebarTreeForMode(
  mode?: TenantApplicationMode,
  grantedPermissions?: ReadonlySet<string>,
): readonly TenantSidebarBranch[] {
  return buildTenantSidebarTree(getTenantRoutesForMode(tenantRoutes, mode), grantedPermissions);
}
