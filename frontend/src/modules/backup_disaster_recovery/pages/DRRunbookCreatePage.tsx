import { useMutation } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { MODULE_PATHS, ModuleErrorState, MutationError, PageHeader, PageShell, PageSkeleton } from '../components/ModuleUi';
import { RunbookForm, blankRunbookValues } from '../components/RunbookForm';
import { backupDisasterRecoveryService } from '../services/backup_disaster_recovery-service';
import { useBackupDisasterRecoveryConfiguration } from '../hooks/useBackupDisasterRecoveryConfiguration';

export const DRRunbookCreatePage = () => {
  const navigate = useNavigate();
  const mutation = useMutation({ mutationFn: backupDisasterRecoveryService.createRunbook, onSuccess: (runbook) => navigate(`${MODULE_PATHS.runbooks}/${runbook.id}/edit`) });
  const configuration = useBackupDisasterRecoveryConfiguration();
  if (configuration.isLoading) return <PageSkeleton />;
  if (configuration.error) return <ModuleErrorState error={configuration.error} onRetry={() => { void configuration.refetch(); }} />;
  if (!configuration.data) return <PageSkeleton />;
  const error = mutation.error instanceof Error ? mutation.error : null;
  return <PageShell><PageHeader title="Create a DR runbook" description="Define recovery objectives first, then build and validate its ordered steps." parentLabel="DR runbooks" parentPath={MODULE_PATHS.runbooks} /><MutationError error={error} /><RunbookForm initial={blankRunbookValues(configuration.data.document.runbooks)} submitting={mutation.isPending} serverError={error} submitLabel="Create draft" onCancel={() => navigate(MODULE_PATHS.runbooks)} onSubmit={(payload) => mutation.mutate(payload)} /></PageShell>;
};
