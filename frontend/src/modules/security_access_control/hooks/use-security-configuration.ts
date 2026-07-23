import { useQuery } from "@tanstack/react-query";
import { QUERY_KEYS } from "../contracts";
import { securityService } from "../services/security-service";

/** The sole frontend read path for tenant-owned security behavior. */
export function useSecurityConfiguration() {
  return useQuery({
    queryKey: QUERY_KEYS.configuration(),
    queryFn: () => securityService.configuration.get(),
  });
}
