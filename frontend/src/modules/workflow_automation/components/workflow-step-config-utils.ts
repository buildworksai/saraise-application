import type {
  ActionStepConfig,
  DecisionStepConfig,
  HandlerDescriptorDTO,
  WorkflowStepWriteDTO,
} from "../contracts";

export function actionDescriptorForStep(
  step: WorkflowStepWriteDTO,
  actions: readonly HandlerDescriptorDTO[] | undefined
): HandlerDescriptorDTO | undefined {
  if (step.step_type !== "action") return undefined;
  const config = step.config as ActionStepConfig;
  return actions?.find((descriptor) => descriptor.key === config.handler);
}

export function actionConfigurationForStep(
  step: WorkflowStepWriteDTO
): NonNullable<ActionStepConfig["configuration"]> {
  if (step.step_type !== "action") return {};
  return (step.config as ActionStepConfig).configuration ?? {};
}

export function decisionConfigForStep(step: WorkflowStepWriteDTO): DecisionStepConfig | null {
  if (step.step_type !== "decision" || !("condition" in step.config)) return null;
  return step.config;
}

export function conditionHandlerValue(config: DecisionStepConfig): string {
  const handler = config.condition.handler;
  return typeof handler === "string" ? handler : "";
}
