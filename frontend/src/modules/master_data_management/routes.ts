import { lazy } from "react";
import { DatabaseZap } from "lucide-react";
import type { TenantRoute } from "@/navigation/tenant-route-types";

const modes = ["development", "self-hosted", "saas"] as const;
const parentRouteId = "master-data-management.dashboard";
const pages = {
  dashboard: lazy(() => import("./pages/MasterDataDashboardPage").then(({ MasterDataDashboardPage }) => ({ default: MasterDataDashboardPage }))),
  entityTypes: lazy(() => import("./pages/EntityTypeListPage").then(({ EntityTypeListPage }) => ({ default: EntityTypeListPage }))),
  entityTypeCreate: lazy(() => import("./pages/CreateEntityTypePage").then(({ CreateEntityTypePage }) => ({ default: CreateEntityTypePage }))),
  entityTypeDetail: lazy(() => import("./pages/EntityTypeDetailPage").then(({ EntityTypeDetailPage }) => ({ default: EntityTypeDetailPage }))),
  entityTypeEdit: lazy(() => import("./pages/EditEntityTypePage").then(({ EditEntityTypePage }) => ({ default: EditEntityTypePage }))),
  entities: lazy(() => import("./pages/MasterDataEntityListPage").then(({ MasterDataEntityListPage }) => ({ default: MasterDataEntityListPage }))),
  entityCreate: lazy(() => import("./pages/CreateMasterDataEntityPage").then(({ CreateMasterDataEntityPage }) => ({ default: CreateMasterDataEntityPage }))),
  entityDetail: lazy(() => import("./pages/MasterDataEntityDetailPage").then(({ MasterDataEntityDetailPage }) => ({ default: MasterDataEntityDetailPage }))),
  entityEdit: lazy(() => import("./pages/EditMasterDataEntityPage").then(({ EditMasterDataEntityPage }) => ({ default: EditMasterDataEntityPage }))),
  entityVersion: lazy(() => import("./pages/EntityVersionPage").then(({ EntityVersionPage }) => ({ default: EntityVersionPage }))),
  qualityRules: lazy(() => import("./pages/QualityRuleListPage").then(({ QualityRuleListPage }) => ({ default: QualityRuleListPage }))),
  qualityRuleCreate: lazy(() => import("./pages/CreateQualityRulePage").then(({ CreateQualityRulePage }) => ({ default: CreateQualityRulePage }))),
  qualityRuleDetail: lazy(() => import("./pages/QualityRuleDetailPage").then(({ QualityRuleDetailPage }) => ({ default: QualityRuleDetailPage }))),
  qualityRuleEdit: lazy(() => import("./pages/EditQualityRulePage").then(({ EditQualityRulePage }) => ({ default: EditQualityRulePage }))),
  qualityIssues: lazy(() => import("./pages/QualityIssueListPage").then(({ QualityIssueListPage }) => ({ default: QualityIssueListPage }))),
  qualityIssueDetail: lazy(() => import("./pages/QualityIssueDetailPage").then(({ QualityIssueDetailPage }) => ({ default: QualityIssueDetailPage }))),
  matchingRules: lazy(() => import("./pages/MatchingRuleListPage").then(({ MatchingRuleListPage }) => ({ default: MatchingRuleListPage }))),
  matchingRuleCreate: lazy(() => import("./pages/CreateMatchingRulePage").then(({ CreateMatchingRulePage }) => ({ default: CreateMatchingRulePage }))),
  matchingRuleDetail: lazy(() => import("./pages/MatchingRuleDetailPage").then(({ MatchingRuleDetailPage }) => ({ default: MatchingRuleDetailPage }))),
  matchingRuleEdit: lazy(() => import("./pages/EditMatchingRulePage").then(({ EditMatchingRulePage }) => ({ default: EditMatchingRulePage }))),
  matches: lazy(() => import("./pages/MatchCandidateListPage").then(({ MatchCandidateListPage }) => ({ default: MatchCandidateListPage }))),
  matchDetail: lazy(() => import("./pages/MatchCandidateDetailPage").then(({ MatchCandidateDetailPage }) => ({ default: MatchCandidateDetailPage }))),
  merges: lazy(() => import("./pages/MergeHistoryListPage").then(({ MergeHistoryListPage }) => ({ default: MergeHistoryListPage }))),
  mergeDetail: lazy(() => import("./pages/MergeHistoryDetailPage").then(({ MergeHistoryDetailPage }) => ({ default: MergeHistoryDetailPage }))),
  jobDetail: lazy(() => import("./pages/AsyncJobDetailPage").then(({ AsyncJobDetailPage }) => ({ default: AsyncJobDetailPage }))),
} as const;

function contextual(id: string, path: string, page: keyof typeof pages, sourceFile: string): TenantRoute {
  return { id: `master-data-management.${id}`, module: "master_data_management", path, sourceFile: `modules/master_data_management/pages/${sourceFile}`, Page: pages[page], modes, navigation: { type: "contextual", parentRouteId } };
}

export const tenantRoutes = [
  { id: parentRouteId, module: "master_data_management", path: "/master-data", sourceFile: "modules/master_data_management/pages/MasterDataDashboardPage.tsx", Page: pages.dashboard, modes, navigation: { type: "sidebar", label: "Master data", icon: DatabaseZap, order: 240 } },
  contextual("entity-types.list", "/master-data/entity-types", "entityTypes", "EntityTypeListPage.tsx"),
  contextual("entity-types.create", "/master-data/entity-types/new", "entityTypeCreate", "CreateEntityTypePage.tsx"),
  contextual("entity-types.detail", "/master-data/entity-types/:id", "entityTypeDetail", "EntityTypeDetailPage.tsx"),
  contextual("entity-types.edit", "/master-data/entity-types/:id/edit", "entityTypeEdit", "EditEntityTypePage.tsx"),
  contextual("entities.list", "/master-data/entities", "entities", "MasterDataEntityListPage.tsx"),
  contextual("entities.create", "/master-data/entities/new", "entityCreate", "CreateMasterDataEntityPage.tsx"),
  contextual("entities.detail", "/master-data/entities/:id", "entityDetail", "MasterDataEntityDetailPage.tsx"),
  contextual("entities.edit", "/master-data/entities/:id/edit", "entityEdit", "EditMasterDataEntityPage.tsx"),
  contextual("entities.version", "/master-data/entities/:id/versions/:version", "entityVersion", "EntityVersionPage.tsx"),
  contextual("quality.rules.list", "/master-data/quality/rules", "qualityRules", "QualityRuleListPage.tsx"),
  contextual("quality.rules.create", "/master-data/quality/rules/new", "qualityRuleCreate", "CreateQualityRulePage.tsx"),
  contextual("quality.rules.detail", "/master-data/quality/rules/:id", "qualityRuleDetail", "QualityRuleDetailPage.tsx"),
  contextual("quality.rules.edit", "/master-data/quality/rules/:id/edit", "qualityRuleEdit", "EditQualityRulePage.tsx"),
  contextual("quality.issues.list", "/master-data/quality/issues", "qualityIssues", "QualityIssueListPage.tsx"),
  contextual("quality.issues.detail", "/master-data/quality/issues/:id", "qualityIssueDetail", "QualityIssueDetailPage.tsx"),
  contextual("matching.rules.list", "/master-data/matching/rules", "matchingRules", "MatchingRuleListPage.tsx"),
  contextual("matching.rules.create", "/master-data/matching/rules/new", "matchingRuleCreate", "CreateMatchingRulePage.tsx"),
  contextual("matching.rules.detail", "/master-data/matching/rules/:id", "matchingRuleDetail", "MatchingRuleDetailPage.tsx"),
  contextual("matching.rules.edit", "/master-data/matching/rules/:id/edit", "matchingRuleEdit", "EditMatchingRulePage.tsx"),
  contextual("matches.list", "/master-data/matches", "matches", "MatchCandidateListPage.tsx"),
  contextual("matches.detail", "/master-data/matches/:id", "matchDetail", "MatchCandidateDetailPage.tsx"),
  contextual("merges.list", "/master-data/merges", "merges", "MergeHistoryListPage.tsx"),
  contextual("merges.detail", "/master-data/merges/:id", "mergeDetail", "MergeHistoryDetailPage.tsx"),
  contextual("jobs.detail", "/master-data/jobs/:id", "jobDetail", "AsyncJobDetailPage.tsx"),
] satisfies readonly TenantRoute[];

export default tenantRoutes;
