import { useQuery } from '@tanstack/react-query';
import { crmKeys, crmService } from '../services/crm-service';

/** Tenant configuration is required runtime data; callers must render errors, never local defaults. */
export function useCrmConfiguration() {
  return useQuery({
    queryKey: crmKeys.configuration(),
    queryFn: crmService.getConfiguration,
    staleTime: 30_000,
    retry: 1,
  });
}
