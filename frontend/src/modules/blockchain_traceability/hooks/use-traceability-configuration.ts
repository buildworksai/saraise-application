import { useQuery } from '@tanstack/react-query';
import { blockchainTraceabilityService } from '../services/blockchain_traceability-service';

export const traceabilityConfigurationKey = ['blockchain-traceability', 'configuration'] as const;
export const traceabilityCapabilitiesKey = ['blockchain-traceability', 'capabilities'] as const;

export function useTraceabilityConfiguration(environment?: string) {
  return useQuery({
    queryKey: [...traceabilityConfigurationKey, environment],
    queryFn: () => blockchainTraceabilityService.getConfiguration(environment),
  });
}

export function useTraceabilityCapabilities(environment?: string) {
  return useQuery({
    queryKey: [...traceabilityCapabilitiesKey, environment],
    queryFn: () => blockchainTraceabilityService.getCapabilities(environment),
  });
}
