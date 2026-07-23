import { useQuery } from "@tanstack/react-query";
import type { ConfigurationEnvironment } from "../contracts";
import { aiAgentService } from "../services/ai-agent-service";

export function useAiAgentConfiguration(environment: ConfigurationEnvironment = "production") {
  return useQuery({
    queryKey: ["ai-agent-management", "configuration", environment],
    queryFn: () => aiAgentService.getConfiguration(environment),
    staleTime: 30_000,
  });
}
