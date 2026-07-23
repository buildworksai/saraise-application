import { useQuery } from "@tanstack/react-query";
import { customizationFrameworkService as service } from "../services/customization-framework-service";

/** One tenant-scoped source for every runtime preference consumed by module pages. */
export function useRuntimeConfiguration() {
  return useQuery({
    queryKey: ["customization", "runtime-configuration"],
    queryFn: service.getConfiguration,
    staleTime: 30_000,
  });
}
