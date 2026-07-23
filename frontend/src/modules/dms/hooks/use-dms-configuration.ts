import { useQuery } from '@tanstack/react-query';
import type { DmsConfigurationValues, DmsUploadTransportPolicy } from '../contracts';
import { DMS_QUERY_KEYS, dmsService } from '../services/dms-service';

/** Tenant configuration is mandatory; callers must render query failures and never invent defaults. */
export function useDmsConfiguration() {
  return useQuery({
    queryKey: DMS_QUERY_KEYS.configuration(),
    queryFn: () => dmsService.getConfiguration(),
  });
}

export function uploadTransportPolicy(values: DmsConfigurationValues): DmsUploadTransportPolicy {
  return {
    timeout_ms: values.upload_timeout_ms,
    max_retries: values.upload_max_retries,
    circuit_breaker_failure_threshold: values.circuit_breaker_failure_threshold,
    circuit_breaker_reset_ms: values.circuit_breaker_reset_ms,
  };
}
