import { useQuery } from "@tanstack/react-query";
import { masterDataService } from "../services/master-data-service";

/**
 * Configuration is authoritative tenant data. Consumers render loading/failure
 * states instead of silently substituting source-code business defaults.
 */
export function useMasterDataConfiguration() {
  return useQuery({
    queryKey: ["mdm", "configuration"] as const,
    queryFn: () => masterDataService.configuration.current(),
    staleTime: 30_000,
  });
}
