import { useMutation } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { MODULE_PATHS, MutationError, PageHeader, PageShell } from '../components/ModuleUi';
import { RunbookForm, blankRunbookValues } from '../components/RunbookForm';
import { backupDisasterRecoveryService } from '../services/backup_disaster_recovery-service';

export const DRRunbookCreatePage = () => {
  const navigate = useNavigate();
  const mutation = useMutation({ mutationFn: backupDisasterRecoveryService.createRunbook, onSuccess: (runbook) => navigate(`${MODULE_PATHS.runbooks}/${runbook.id}/edit`) });
  const error = mutation.error instanceof Error ? mutation.error : null;
  return <PageShell><PageHeader title="Create a DR runbook" description="Define recovery objectives first, then build and validate its ordered steps." parentLabel="DR runbooks" parentPath={MODULE_PATHS.runbooks} /><MutationError error={error} /><RunbookForm initial={blankRunbookValues} submitting={mutation.isPending} serverError={error} submitLabel="Create draft" onCancel={() => navigate(MODULE_PATHS.runbooks)} onSubmit={(payload) => mutation.mutate(payload)} /></PageShell>;
};
