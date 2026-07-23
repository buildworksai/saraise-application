import { useQuery } from '@tanstack/react-query';
import { hrKeys } from '../contracts';
import { hrService } from '../services/hr-service';

/** Configuration is required business data. Consumers fail closed while it is unavailable. */
export function useHumanResourcesConfiguration() {
  return useQuery({
    queryKey: hrKeys.configuration,
    queryFn: () => hrService.getConfiguration(),
    staleTime: 60_000,
  });
}
