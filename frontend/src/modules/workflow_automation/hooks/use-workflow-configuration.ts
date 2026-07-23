import { useQuery } from "@tanstack/react-query";
import type { WorkflowConfigurationDTO } from "../contracts";
import { workflowService } from "../services/workflow-service";

export function useWorkflowConfiguration(
  environment: WorkflowConfigurationDTO["environment"] = "production",
) {
  return useQuery({
    queryKey: ["workflow-automation", "configuration", environment],
    queryFn: () => workflowService.configuration.get(environment),
    staleTime: 60_000,
  });
}
