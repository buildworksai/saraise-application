import { lazy } from "react";
import {
  Archive,
  CalendarClock,
  DatabaseBackup,
  LayoutDashboard,
  ShieldCheck,
  Target,
  TimerReset,
} from "lucide-react";
import type { TenantRoute } from "@/navigation/tenant-route-types";

const modes = ["development", "self-hosted", "saas"] as const;
const contextual = (parentRouteId: string) => ({ type: "contextual" as const, parentRouteId });

export const tenantRoutes = [
  {
    id: "backup_recovery.overview",
    module: "backup_recovery",
    path: "/backup-recovery",
    sourceFile: "modules/backup_recovery/pages/BackupRecoveryOverviewPage.tsx",
    Page: lazy(() =>
      import("./pages/BackupRecoveryOverviewPage").then(({ BackupRecoveryOverviewPage }) => ({
        default: BackupRecoveryOverviewPage,
      }))
    ),
    modes,
    navigation: { type: "sidebar", label: "Backup overview", icon: LayoutDashboard, order: 470 },
  },
  {
    id: "backup_recovery.jobs.list",
    module: "backup_recovery",
    path: "/backup-recovery/jobs",
    sourceFile: "modules/backup_recovery/pages/BackupJobListPage.tsx",
    Page: lazy(() =>
      import("./pages/BackupJobListPage").then(({ BackupJobListPage }) => ({
        default: BackupJobListPage,
      }))
    ),
    modes,
    navigation: { type: "sidebar", label: "Backup jobs", icon: DatabaseBackup, order: 471 },
  },
  {
    id: "backup_recovery.jobs.create",
    module: "backup_recovery",
    path: "/backup-recovery/jobs/new",
    sourceFile: "modules/backup_recovery/pages/BackupJobCreatePage.tsx",
    Page: lazy(() =>
      import("./pages/BackupJobCreatePage").then(({ BackupJobCreatePage }) => ({
        default: BackupJobCreatePage,
      }))
    ),
    modes,
    navigation: contextual("backup_recovery.jobs.list"),
  },
  {
    id: "backup_recovery.jobs.detail",
    module: "backup_recovery",
    path: "/backup-recovery/jobs/:id",
    sourceFile: "modules/backup_recovery/pages/BackupJobDetailPage.tsx",
    Page: lazy(() =>
      import("./pages/BackupJobDetailPage").then(({ BackupJobDetailPage }) => ({
        default: BackupJobDetailPage,
      }))
    ),
    modes,
    navigation: contextual("backup_recovery.jobs.list"),
  },
  {
    id: "backup_recovery.jobs.edit",
    module: "backup_recovery",
    path: "/backup-recovery/jobs/:id/edit",
    sourceFile: "modules/backup_recovery/pages/BackupJobEditPage.tsx",
    Page: lazy(() =>
      import("./pages/BackupJobEditPage").then(({ BackupJobEditPage }) => ({
        default: BackupJobEditPage,
      }))
    ),
    modes,
    navigation: contextual("backup_recovery.jobs.list"),
  },
  {
    id: "backup_recovery.schedules.list",
    module: "backup_recovery",
    path: "/backup-recovery/schedules",
    sourceFile: "modules/backup_recovery/pages/BackupScheduleListPage.tsx",
    Page: lazy(() =>
      import("./pages/BackupScheduleListPage").then(({ BackupScheduleListPage }) => ({
        default: BackupScheduleListPage,
      }))
    ),
    modes,
    navigation: { type: "sidebar", label: "Backup schedules", icon: CalendarClock, order: 472 },
  },
  {
    id: "backup_recovery.schedules.create",
    module: "backup_recovery",
    path: "/backup-recovery/schedules/new",
    sourceFile: "modules/backup_recovery/pages/BackupScheduleCreatePage.tsx",
    Page: lazy(() =>
      import("./pages/BackupScheduleCreatePage").then(({ BackupScheduleCreatePage }) => ({
        default: BackupScheduleCreatePage,
      }))
    ),
    modes,
    navigation: contextual("backup_recovery.schedules.list"),
  },
  {
    id: "backup_recovery.schedules.detail",
    module: "backup_recovery",
    path: "/backup-recovery/schedules/:id",
    sourceFile: "modules/backup_recovery/pages/BackupScheduleDetailPage.tsx",
    Page: lazy(() =>
      import("./pages/BackupScheduleDetailPage").then(({ BackupScheduleDetailPage }) => ({
        default: BackupScheduleDetailPage,
      }))
    ),
    modes,
    navigation: contextual("backup_recovery.schedules.list"),
  },
  {
    id: "backup_recovery.schedules.edit",
    module: "backup_recovery",
    path: "/backup-recovery/schedules/:id/edit",
    sourceFile: "modules/backup_recovery/pages/BackupScheduleEditPage.tsx",
    Page: lazy(() =>
      import("./pages/BackupScheduleEditPage").then(({ BackupScheduleEditPage }) => ({
        default: BackupScheduleEditPage,
      }))
    ),
    modes,
    navigation: contextual("backup_recovery.schedules.list"),
  },
  {
    id: "backup_recovery.retention.list",
    module: "backup_recovery",
    path: "/backup-recovery/retention-policies",
    sourceFile: "modules/backup_recovery/pages/BackupRetentionPolicyListPage.tsx",
    Page: lazy(() =>
      import("./pages/BackupRetentionPolicyListPage").then(({ BackupRetentionPolicyListPage }) => ({
        default: BackupRetentionPolicyListPage,
      }))
    ),
    modes,
    navigation: { type: "sidebar", label: "Backup retention", icon: TimerReset, order: 473 },
  },
  {
    id: "backup_recovery.retention.create",
    module: "backup_recovery",
    path: "/backup-recovery/retention-policies/new",
    sourceFile: "modules/backup_recovery/pages/BackupRetentionPolicyCreatePage.tsx",
    Page: lazy(() =>
      import("./pages/BackupRetentionPolicyCreatePage").then(
        ({ BackupRetentionPolicyCreatePage }) => ({ default: BackupRetentionPolicyCreatePage })
      )
    ),
    modes,
    navigation: contextual("backup_recovery.retention.list"),
  },
  {
    id: "backup_recovery.retention.detail",
    module: "backup_recovery",
    path: "/backup-recovery/retention-policies/:id",
    sourceFile: "modules/backup_recovery/pages/BackupRetentionPolicyDetailPage.tsx",
    Page: lazy(() =>
      import("./pages/BackupRetentionPolicyDetailPage").then(
        ({ BackupRetentionPolicyDetailPage }) => ({ default: BackupRetentionPolicyDetailPage })
      )
    ),
    modes,
    navigation: contextual("backup_recovery.retention.list"),
  },
  {
    id: "backup_recovery.retention.edit",
    module: "backup_recovery",
    path: "/backup-recovery/retention-policies/:id/edit",
    sourceFile: "modules/backup_recovery/pages/BackupRetentionPolicyEditPage.tsx",
    Page: lazy(() =>
      import("./pages/BackupRetentionPolicyEditPage").then(({ BackupRetentionPolicyEditPage }) => ({
        default: BackupRetentionPolicyEditPage,
      }))
    ),
    modes,
    navigation: contextual("backup_recovery.retention.list"),
  },
  {
    id: "backup_recovery.targets.list",
    module: "backup_recovery",
    path: "/backup-recovery/storage-targets",
    sourceFile: "modules/backup_recovery/pages/BackupStorageTargetListPage.tsx",
    Page: lazy(() =>
      import("./pages/BackupStorageTargetListPage").then(({ BackupStorageTargetListPage }) => ({
        default: BackupStorageTargetListPage,
      }))
    ),
    modes,
    navigation: { type: "sidebar", label: "Backup storage", icon: Target, order: 474 },
  },
  {
    id: "backup_recovery.targets.create",
    module: "backup_recovery",
    path: "/backup-recovery/storage-targets/new",
    sourceFile: "modules/backup_recovery/pages/BackupStorageTargetCreatePage.tsx",
    Page: lazy(() =>
      import("./pages/BackupStorageTargetCreatePage").then(({ BackupStorageTargetCreatePage }) => ({
        default: BackupStorageTargetCreatePage,
      }))
    ),
    modes,
    navigation: contextual("backup_recovery.targets.list"),
  },
  {
    id: "backup_recovery.targets.detail",
    module: "backup_recovery",
    path: "/backup-recovery/storage-targets/:id",
    sourceFile: "modules/backup_recovery/pages/BackupStorageTargetDetailPage.tsx",
    Page: lazy(() =>
      import("./pages/BackupStorageTargetDetailPage").then(({ BackupStorageTargetDetailPage }) => ({
        default: BackupStorageTargetDetailPage,
      }))
    ),
    modes,
    navigation: contextual("backup_recovery.targets.list"),
  },
  {
    id: "backup_recovery.targets.edit",
    module: "backup_recovery",
    path: "/backup-recovery/storage-targets/:id/edit",
    sourceFile: "modules/backup_recovery/pages/BackupStorageTargetEditPage.tsx",
    Page: lazy(() =>
      import("./pages/BackupStorageTargetEditPage").then(({ BackupStorageTargetEditPage }) => ({
        default: BackupStorageTargetEditPage,
      }))
    ),
    modes,
    navigation: contextual("backup_recovery.targets.list"),
  },
  {
    id: "backup_recovery.archives.list",
    module: "backup_recovery",
    path: "/backup-recovery/archives",
    sourceFile: "modules/backup_recovery/pages/BackupArchiveListPage.tsx",
    Page: lazy(() =>
      import("./pages/BackupArchiveListPage").then(({ BackupArchiveListPage }) => ({
        default: BackupArchiveListPage,
      }))
    ),
    modes,
    navigation: { type: "sidebar", label: "Backup artifacts", icon: Archive, order: 475 },
  },
  {
    id: "backup_recovery.archives.detail",
    module: "backup_recovery",
    path: "/backup-recovery/archives/:id",
    sourceFile: "modules/backup_recovery/pages/BackupArchiveDetailPage.tsx",
    Page: lazy(() =>
      import("./pages/BackupArchiveDetailPage").then(({ BackupArchiveDetailPage }) => ({
        default: BackupArchiveDetailPage,
      }))
    ),
    modes,
    navigation: contextual("backup_recovery.archives.list"),
  },
  {
    id: "backup_recovery.verifications.list",
    module: "backup_recovery",
    path: "/backup-recovery/verifications",
    sourceFile: "modules/backup_recovery/pages/BackupVerificationListPage.tsx",
    Page: lazy(() =>
      import("./pages/BackupVerificationListPage").then(({ BackupVerificationListPage }) => ({
        default: BackupVerificationListPage,
      }))
    ),
    modes,
    navigation: { type: "sidebar", label: "Backup verification", icon: ShieldCheck, order: 476 },
  },
  {
    id: "backup_recovery.verifications.detail",
    module: "backup_recovery",
    path: "/backup-recovery/verifications/:id",
    sourceFile: "modules/backup_recovery/pages/BackupVerificationDetailPage.tsx",
    Page: lazy(() =>
      import("./pages/BackupVerificationDetailPage").then(({ BackupVerificationDetailPage }) => ({
        default: BackupVerificationDetailPage,
      }))
    ),
    modes,
    navigation: contextual("backup_recovery.verifications.list"),
  },
] satisfies readonly TenantRoute[];

export default tenantRoutes;
