/**
 * Backup & Recovery (Extended) Module
 * 
 * Exports all public components and services.
 */

export { BackupJobListPage } from './pages/BackupJobListPage';
export { BackupJobDetailPage } from './pages/BackupJobDetailPage';
export { BackupScheduleListPage } from './pages/BackupScheduleListPage';
export { BackupScheduleDetailPage } from './pages/BackupScheduleDetailPage';
export { BackupRetentionPolicyPage } from './pages/BackupRetentionPolicyPage';
export { BackupArchivePage } from './pages/BackupArchivePage';
export { backupRecoveryService } from './services/backup-recovery-service';
export * from './contracts';
