import { lazy } from "react";
import { DatabaseZap, Settings2 } from "lucide-react";
import type { TenantRoute } from "@/navigation/tenant-route-types";

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
  configuration: lazy(() => import("./pages/MasterDataConfigurationPage").then(({ MasterDataConfigurationPage }) => ({ default: MasterDataConfigurationPage }))),
} as const;

function registered(id: string, path: string, title: string, label: string, page: keyof typeof pages, sourceFile: string, navigationPath?: string): TenantRoute {
  return {
    id: `master-data-management.${id}`,
    module: "master_data_management",
    path,
    title,
    sourceFile: `modules/master_data_management/pages/${sourceFile}`,
    Page: pages[page],
    navigation: { type: "sidebar", label, icon: DatabaseZap, order: Number.MAX_SAFE_INTEGER, ...(navigationPath ? { path: navigationPath } : {}) },
  };
}

export const tenantRoutes = [
  registered("dashboard", "/master-data", "Master data stewardship", "Overview", "dashboard", "MasterDataDashboardPage.tsx"),
  registered("entity-types.list", "/master-data/entity-types", "Master entity types", "Entity types", "entityTypes", "EntityTypeListPage.tsx"),
  registered("entity-types.create", "/master-data/entity-types/new", "Create master entity type", "Create entity type", "entityTypeCreate", "CreateEntityTypePage.tsx"),
  registered("entity-types.detail", "/master-data/entity-types/:id", "Master entity type details", "Entity type details", "entityTypeDetail", "EntityTypeDetailPage.tsx", "/master-data/entity-types"),
  registered("entity-types.edit", "/master-data/entity-types/:id/edit", "Edit master entity type", "Edit entity type", "entityTypeEdit", "EditEntityTypePage.tsx", "/master-data/entity-types"),
  registered("entities.list", "/master-data/entities", "Master data entities", "Entities", "entities", "MasterDataEntityListPage.tsx"),
  registered("entities.create", "/master-data/entities/new", "Create master data entity", "Create entity", "entityCreate", "CreateMasterDataEntityPage.tsx"),
  registered("entities.detail", "/master-data/entities/:id", "Master data entity details", "Entity details", "entityDetail", "MasterDataEntityDetailPage.tsx", "/master-data/entities"),
  registered("entities.edit", "/master-data/entities/:id/edit", "Edit master data entity", "Edit entity", "entityEdit", "EditMasterDataEntityPage.tsx", "/master-data/entities"),
  registered("entities.version", "/master-data/entities/:id/versions/:version", "Master data entity version", "Entity version", "entityVersion", "EntityVersionPage.tsx", "/master-data/entities"),
  registered("quality.rules.list", "/master-data/quality/rules", "Master data quality rules", "Quality rules", "qualityRules", "QualityRuleListPage.tsx"),
  registered("quality.rules.create", "/master-data/quality/rules/new", "Create quality rule", "Create quality rule", "qualityRuleCreate", "CreateQualityRulePage.tsx"),
  registered("quality.rules.detail", "/master-data/quality/rules/:id", "Quality rule details", "Quality rule details", "qualityRuleDetail", "QualityRuleDetailPage.tsx", "/master-data/quality/rules"),
  registered("quality.rules.edit", "/master-data/quality/rules/:id/edit", "Edit quality rule", "Edit quality rule", "qualityRuleEdit", "EditQualityRulePage.tsx", "/master-data/quality/rules"),
  registered("quality.issues.list", "/master-data/quality/issues", "Master data quality issues", "Quality issues", "qualityIssues", "QualityIssueListPage.tsx"),
  registered("quality.issues.detail", "/master-data/quality/issues/:id", "Quality issue details", "Quality issue details", "qualityIssueDetail", "QualityIssueDetailPage.tsx", "/master-data/quality/issues"),
  registered("matching.rules.list", "/master-data/matching/rules", "Master data matching rules", "Matching rules", "matchingRules", "MatchingRuleListPage.tsx"),
  registered("matching.rules.create", "/master-data/matching/rules/new", "Create matching rule", "Create matching rule", "matchingRuleCreate", "CreateMatchingRulePage.tsx"),
  registered("matching.rules.detail", "/master-data/matching/rules/:id", "Matching rule details", "Matching rule details", "matchingRuleDetail", "MatchingRuleDetailPage.tsx", "/master-data/matching/rules"),
  registered("matching.rules.edit", "/master-data/matching/rules/:id/edit", "Edit matching rule", "Edit matching rule", "matchingRuleEdit", "EditMatchingRulePage.tsx", "/master-data/matching/rules"),
  registered("matches.list", "/master-data/matches", "Duplicate match candidates", "Duplicate review", "matches", "MatchCandidateListPage.tsx"),
  registered("matches.detail", "/master-data/matches/:id", "Duplicate match candidate details", "Match details", "matchDetail", "MatchCandidateDetailPage.tsx", "/master-data/matches"),
  registered("merges.list", "/master-data/merges", "Master data merge history", "Merge history", "merges", "MergeHistoryListPage.tsx"),
  registered("merges.detail", "/master-data/merges/:id", "Master data merge provenance", "Merge details", "mergeDetail", "MergeHistoryDetailPage.tsx", "/master-data/merges"),
  registered("jobs.detail", "/master-data/jobs/:id", "Master data job details", "Job details", "jobDetail", "AsyncJobDetailPage.tsx", "/master-data"),
  { ...registered("configuration", "/master-data/configuration", "Master data configuration", "Configuration", "configuration", "MasterDataConfigurationPage.tsx"), requiredPermission: "mdm.configuration:manage", navigation: { type: "sidebar", label: "Configuration", icon: Settings2, order: Number.MAX_SAFE_INTEGER } },
] satisfies readonly TenantRoute[];

export default tenantRoutes;
