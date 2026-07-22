import { useQuery } from '@tanstack/react-query';
import { backupDisasterRecoveryService } from '../services/backup_disaster_recovery-service';

export const configurationQueryKey = ['bdr', 'configuration'] as const;

export const useBackupDisasterRecoveryConfiguration = () => useQuery({
  queryKey: configurationQueryKey,
  queryFn: backupDisasterRecoveryService.getConfiguration,
});
