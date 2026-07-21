import { useQuery } from "@tanstack/react-query";
import type {
  DefinitionFilters,
  RunFilters,
  RunStatus,
  ScheduleFilters,
  TaskRunFilters,
} from "../contracts";
import { automationOrchestrationService as service } from "../services/automation-orchestration-service";

export const orchestrationKeys = {
  all: ["automation-orchestration"] as const,
  definitions: (filters: DefinitionFilters) => [...orchestrationKeys.all, "definitions", filters] as const,
  definition: (id: string) => [...orchestrationKeys.all, "definition", id] as const,
  nodeTypes: () => [...orchestrationKeys.all, "node-types"] as const,
  schedules: (filters: ScheduleFilters) => [...orchestrationKeys.all, "schedules", filters] as const,
  schedule: (id: string) => [...orchestrationKeys.all, "schedule", id] as const,
  runs: (filters: RunFilters) => [...orchestrationKeys.all, "runs", filters] as const,
  run: (id: string) => [...orchestrationKeys.all, "run", id] as const,
  taskRuns: (runId: string, filters: TaskRunFilters) =>
    [...orchestrationKeys.all, "task-runs", runId, filters] as const,
  events: (runId: string) => [...orchestrationKeys.all, "events", runId] as const,
};

const NONTERMINAL_RUNS: readonly RunStatus[] = ["queued", "running", "paused", "cancelling"];

export function useDefinitions(filters: DefinitionFilters) {
  return useQuery({
    queryKey: orchestrationKeys.definitions(filters),
    queryFn: () => service.listDefinitions(filters),
  });
}

export function useDefinition(id: string) {
  return useQuery({
    queryKey: orchestrationKeys.definition(id),
    queryFn: () => service.getDefinition(id),
    enabled: Boolean(id),
  });
}

export function useNodeTypes(enabled = true) {
  return useQuery({
    queryKey: orchestrationKeys.nodeTypes(),
    queryFn: () => service.listNodeTypes(),
    select: (result) => result.items,
    enabled,
  });
}

export function useSchedules(filters: ScheduleFilters) {
  return useQuery({
    queryKey: orchestrationKeys.schedules(filters),
    queryFn: () => service.listSchedules(filters),
  });
}

export function useSchedule(id: string) {
  return useQuery({
    queryKey: orchestrationKeys.schedule(id),
    queryFn: () => service.getSchedule(id),
    enabled: Boolean(id),
  });
}

export function useRuns(filters: RunFilters) {
  return useQuery({
    queryKey: orchestrationKeys.runs(filters),
    queryFn: () => service.listRuns(filters),
    refetchInterval: (query) => {
      const hasLiveRun = query.state.data?.items.some((run) => NONTERMINAL_RUNS.includes(run.status));
      return hasLiveRun ? 5_000 : false;
    },
  });
}

export function useRun(id: string) {
  return useQuery({
    queryKey: orchestrationKeys.run(id),
    queryFn: () => service.getRun(id),
    enabled: Boolean(id),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && NONTERMINAL_RUNS.includes(status) ? 3_000 : false;
    },
  });
}

export function useTaskRuns(runId: string, filters: TaskRunFilters = {}) {
  return useQuery({
    queryKey: orchestrationKeys.taskRuns(runId, filters),
    queryFn: () => service.listTaskRuns(runId, filters),
    enabled: Boolean(runId),
  });
}

export function useRunEvents(runId: string) {
  return useQuery({
    queryKey: orchestrationKeys.events(runId),
    queryFn: () => service.listEvents(runId),
    select: (result) => result.items,
    enabled: Boolean(runId),
    refetchInterval: 5_000,
  });
}
