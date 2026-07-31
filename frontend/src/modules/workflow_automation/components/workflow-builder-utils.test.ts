/* eslint-disable max-lines-per-function, @typescript-eslint/no-unsafe-assignment -- Utility fixtures intentionally assert full governed workflow payload shapes. */
import { describe, expect, it } from "vitest";
import type { WorkflowConfigurationDocument, WorkflowCreateDTO } from "../contracts";
import {
  moveStepByOffset,
  removeStepAt,
  WORKFLOW_CATALOG_ACTIONS_QUERY_KEY,
  WORKFLOW_CATALOG_ASSIGNEES_QUERY_KEY,
  WORKFLOW_CATALOG_CONDITIONS_QUERY_KEY,
  workflowBuilderIssues,
  workflowBuilderPayload,
  localIssues,
  newStep,
  recipientPath,
  slug,
} from "./workflow-builder-utils";

const policy = {
  defaults: {
    approval_assignment_kind: "role",
    approval_due_seconds: 7200,
    approval_rejection_behavior: "goto",
  },
} as WorkflowConfigurationDocument;

const basePayload: WorkflowCreateDTO = {
  key: "purchase_approval",
  name: "Purchase approval",
  description: "Govern purchasing",
  workflow_type: "approval",
  trigger_type: "manual",
  trigger_config: {},
  required_context_schema: {},
  steps: [
    {
      key: "action",
      name: "Action",
      step_type: "action",
      order: 1,
      config: { handler: "core.action", schema_version: "1", input_mapping: {}, configuration: {} },
      is_terminal: false,
    },
    {
      key: "approval",
      name: "Approval",
      step_type: "approval",
      order: 2,
      config: {
        assignment_kind: "role",
        assignee_id: "role-1",
        due_in_seconds: 7200,
        rejection_behavior: "fail",
        reject_step_key: null,
      },
      is_terminal: false,
    },
    {
      key: "decision",
      name: "Decision",
      step_type: "decision",
      order: 3,
      config: {
        condition: { handler: "core.condition" },
        true_step_key: "approval",
        false_step_key: "action",
      },
      is_terminal: true,
    },
  ],
};

describe("workflow builder utilities", () => {
  it("declares stable workflow catalog query keys", () => {
    expect(WORKFLOW_CATALOG_ACTIONS_QUERY_KEY).toEqual(["workflow-catalog-actions"]);
    expect(WORKFLOW_CATALOG_CONDITIONS_QUERY_KEY).toEqual(["workflow-catalog-conditions"]);
    expect(WORKFLOW_CATALOG_ASSIGNEES_QUERY_KEY).toEqual(["workflow-catalog-assignees"]);
  });

  it("normalizes slugs using lowercase, separator collapse, edge trimming, and maximum length", () => {
    expect(slug("  Emergency PO Approval!!!  ", 64)).toBe("emergency_po_approval");
    expect(slug("__Manual Key / 2026__", 64)).toBe("manual_key_2026");
    expect(slug("___Multi Edge___", 64)).toBe("multi_edge");
    expect(slug("Multi Edge___", 64)).toBe("multi_edge");
    expect(slug("___Multi Edge", 64)).toBe("multi_edge");
    expect(slug("Multi___", 64)).toBe("multi");
    expect(slug("Already_ok", 10)).toBe("already_ok");
    expect(slug("abcdefghijkl", 5)).toBe("abcde");
    expect(slug("!!!", 64)).toBe("");
  });

  it("resolves notification recipient paths by channel and rejects non-string mappings", () => {
    expect(
      recipientPath({
        channel: "email",
        recipient_mapping: { recipient_email: "actor.email" },
        template_key: "t",
      })
    ).toBe("actor.email");
    expect(
      recipientPath({
        channel: "in_app",
        recipient_mapping: { recipient_id: "actor.id" },
        template_key: "t",
      })
    ).toBe("actor.id");
    expect(
      recipientPath({
        channel: "email",
        recipient_mapping: { recipient_email: 42 },
        template_key: "t",
      })
    ).toBe("");
    expect(
      recipientPath({
        channel: "in_app",
        recipient_mapping: { recipient_id: false },
        template_key: "t",
      })
    ).toBe("");
    expect(
      recipientPath({
        channel: "email",
        recipient_mapping: { recipient_id: "actor.id" },
        template_key: "t",
      })
    ).toBe("");
  });

  it("creates governed default steps for every supported step type", () => {
    expect(newStep("action", 1, policy)).toEqual({
      key: "step_1",
      name: "Action 1",
      step_type: "action",
      order: 1,
      config: { handler: "", schema_version: "", input_mapping: {}, configuration: {} },
      is_terminal: false,
    });
    expect(newStep("approval", 2, policy)).toEqual({
      key: "step_2",
      name: "Approval 2",
      step_type: "approval",
      order: 2,
      config: {
        assignment_kind: "role",
        assignee_id: "",
        due_in_seconds: 7200,
        rejection_behavior: "goto",
        reject_step_key: null,
      },
      is_terminal: false,
    });
    expect(newStep("notification", 3, policy)).toEqual({
      key: "step_3",
      name: "Notification 3",
      step_type: "notification",
      order: 3,
      config: {
        channel: "in_app",
        recipient_mapping: { recipient_id: "actor.id" },
        template_key: "workflow.task.created",
      },
      is_terminal: false,
    });
    expect(newStep("decision", 4, policy)).toEqual({
      key: "step_4",
      name: "Decision 4",
      step_type: "decision",
      order: 4,
      config: { condition: {}, true_step_key: "", false_step_key: "" },
      is_terminal: false,
    });
  });

  it("accepts a complete local workflow definition without issues", () => {
    expect(localIssues(basePayload)).toEqual([]);
  });

  it("reports missing workflow identity and empty step collections", () => {
    expect(localIssues({ ...basePayload, key: " ", name: "", steps: [] })).toEqual([
      "Workflow key is required.",
      "Workflow name is required.",
      "Add at least one step.",
    ]);
  });

  it("accepts whitespace-padded workflow identity after trimming", () => {
    expect(
      localIssues({ ...basePayload, key: " purchase_approval ", name: " Purchase approval " })
    ).toEqual([]);
    expect(localIssues({ ...basePayload, key: "purchase_approval", name: "   " })).toEqual([
      "Workflow name is required.",
    ]);
    expect(
      localIssues({
        ...basePayload,
        steps: [{ ...basePayload.steps[1]!, key: "   ", is_terminal: true }],
      })
    ).toEqual(["Step 2 needs a unique key."]);
  });

  it("reports duplicate and blank step keys plus missing step names", () => {
    expect(
      localIssues({
        ...basePayload,
        steps: [
          { ...basePayload.steps[0]!, key: "", name: " " },
          { ...basePayload.steps[1]!, key: "" },
        ],
      })
    ).toEqual([
      "Step 1 needs a unique key.",
      "Step 1 needs a name.",
      "Step 2 needs a unique key.",
      "Mark at least one step as terminal.",
    ]);
  });

  it("reports incomplete action, approval, and decision configuration", () => {
    expect(
      localIssues({
        ...basePayload,
        steps: [
          {
            ...basePayload.steps[0]!,
            config: { handler: "", schema_version: "", input_mapping: {}, configuration: {} },
          },
          {
            ...basePayload.steps[1]!,
            config: {
              assignment_kind: "role",
              assignee_id: "",
              due_in_seconds: 7200,
              rejection_behavior: "fail",
              reject_step_key: null,
            },
          },
          {
            ...basePayload.steps[2]!,
            config: { condition: {}, true_step_key: "", false_step_key: "missing" },
          },
        ],
      })
    ).toEqual([
      "Action: choose an available action.",
      "Approval: choose an assignee.",
      "Decision: choose a condition.",
      "Decision: select a valid true branch.",
      "Decision: select a valid false branch.",
    ]);
  });

  it("reports missing decision condition shapes independently from branch validity", () => {
    expect(
      localIssues({
        ...basePayload,
        steps: [
          basePayload.steps[0]!,
          basePayload.steps[1]!,
          {
            ...basePayload.steps[2]!,
            config: { true_step_key: "approval", false_step_key: "action" } as never,
          },
        ],
      })
    ).toEqual(["Decision: choose a condition."]);
    expect(
      localIssues({
        ...basePayload,
        steps: [
          basePayload.steps[0]!,
          basePayload.steps[1]!,
          {
            ...basePayload.steps[2]!,
            config: {
              condition: { handler: 42 },
              true_step_key: "approval",
              false_step_key: "action",
            },
          },
        ],
      })
    ).toEqual(["Decision: choose a condition."]);
  });

  it("reports true and false branch defects independently", () => {
    expect(
      localIssues({
        ...basePayload,
        steps: [
          basePayload.steps[0]!,
          basePayload.steps[1]!,
          {
            ...basePayload.steps[2]!,
            config: {
              condition: { handler: "core.condition" },
              true_step_key: "missing",
              false_step_key: "action",
            },
          },
        ],
      })
    ).toEqual(["Decision: select a valid true branch."]);
    expect(
      localIssues({
        ...basePayload,
        steps: [
          basePayload.steps[0]!,
          basePayload.steps[1]!,
          {
            ...basePayload.steps[2]!,
            config: {
              condition: { handler: "core.condition" },
              true_step_key: "approval",
              false_step_key: "missing",
            },
          },
        ],
      })
    ).toEqual(["Decision: select a valid false branch."]);
  });

  it("does not require a terminal marker for empty definitions beyond the empty-step issue", () => {
    expect(localIssues({ ...basePayload, steps: [] })).toEqual(["Add at least one step."]);
  });

  it("accepts decision branches that target earlier or later existing steps", () => {
    expect(
      localIssues({
        ...basePayload,
        steps: [
          { ...basePayload.steps[2]!, order: 1 },
          { ...basePayload.steps[0]!, order: 2 },
          { ...basePayload.steps[1]!, order: 3 },
        ],
      })
    ).toEqual([]);
  });

  it("builds create payloads with existing context defaults and rejects missing resolved types", () => {
    expect(
      workflowBuilderPayload({
        key: "purchase_approval",
        name: "Purchase approval",
        description: "Govern purchasing",
        workflowType: "approval",
        triggerType: "manual",
        initial: undefined,
        steps: basePayload.steps,
      })
    ).toEqual(basePayload);
    expect(
      workflowBuilderPayload({
        key: "purchase_approval",
        name: "Purchase approval",
        description: "Govern purchasing",
        workflowType: undefined,
        triggerType: "manual",
        initial: undefined,
        steps: basePayload.steps,
      })
    ).toBeNull();
    expect(
      workflowBuilderPayload({
        key: "purchase_approval",
        name: "Purchase approval",
        description: "Govern purchasing",
        workflowType: "approval",
        triggerType: undefined,
        initial: undefined,
        steps: basePayload.steps,
      })
    ).toBeNull();
    expect(
      workflowBuilderPayload({
        key: "purchase_approval",
        name: "Purchase approval",
        description: "Govern purchasing",
        workflowType: "approval",
        triggerType: "manual",
        initial: {
          id: "workflow-1",
          version: 2,
          status: "draft",
          created_by_name: null,
          published_at: null,
          created_at: "2026-07-21T00:00:00Z",
          updated_at: "2026-07-22T00:00:00Z",
          allowed_actions: [],
          transition_history: [],
          versions: [],
          execution_statistics: {
            total: 0,
            active: 0,
            completed: 0,
            failed: 0,
            completion_rate: null,
          },
          handler_health: [],
          ...basePayload,
          description: "Govern purchasing",
          steps: basePayload.steps.map((step, index) => ({
            ...step,
            id: `step-${index + 1}`,
            timeout_seconds: step.timeout_seconds ?? null,
            timeout_action: step.timeout_action ?? null,
            is_terminal: step.is_terminal ?? false,
            created_at: "2026-07-21T00:00:00Z",
            updated_at: "2026-07-22T00:00:00Z",
          })),
          trigger_config: { source: "event" },
          required_context_schema: { subject: "string" },
        },
        steps: basePayload.steps,
      })
    ).toEqual({
      ...basePayload,
      trigger_config: { source: "event" },
      required_context_schema: { subject: "string" },
    });
  });

  it("adds catalog outage issues only for affected step types", () => {
    expect(
      workflowBuilderIssues({
        payload: null,
        actionCatalogFailed: true,
        conditionCatalogFailed: true,
      })
    ).toEqual(["Workflow configuration is unavailable."]);
    expect(
      workflowBuilderIssues({
        payload: basePayload,
        actionCatalogFailed: true,
        conditionCatalogFailed: true,
      })
    ).toEqual(["Action catalog is unavailable.", "Condition catalog is unavailable."]);
    expect(
      workflowBuilderIssues({
        payload: { ...basePayload, steps: [basePayload.steps[1]!] },
        actionCatalogFailed: true,
        conditionCatalogFailed: true,
      })
    ).toEqual(["Mark at least one step as terminal."]);
    expect(
      workflowBuilderIssues({
        payload: { ...basePayload, steps: [basePayload.steps[0]!] },
        actionCatalogFailed: true,
        conditionCatalogFailed: false,
      })
    ).toEqual(["Mark at least one step as terminal.", "Action catalog is unavailable."]);
    expect(
      workflowBuilderIssues({
        payload: { ...basePayload, steps: [basePayload.steps[0]!] },
        actionCatalogFailed: false,
        conditionCatalogFailed: true,
      })
    ).toEqual(["Mark at least one step as terminal."]);
    expect(
      workflowBuilderIssues({
        payload: { ...basePayload, steps: [basePayload.steps[2]!] },
        actionCatalogFailed: true,
        conditionCatalogFailed: false,
      })
    ).toEqual(["Decision: select a valid true branch.", "Decision: select a valid false branch."]);
    expect(
      workflowBuilderIssues({
        payload: { ...basePayload, steps: [basePayload.steps[2]!] },
        actionCatalogFailed: false,
        conditionCatalogFailed: true,
      })
    ).toEqual([
      "Decision: select a valid true branch.",
      "Decision: select a valid false branch.",
      "Condition catalog is unavailable.",
    ]);
  });

  it("removes and moves steps while preserving one-based order values", () => {
    const removed = removeStepAt(basePayload.steps, 1);
    expect(removed).not.toBe(basePayload.steps);
    expect(removed).toHaveLength(2);
    expect(removed).toEqual([
      { ...basePayload.steps[0]!, order: 1 },
      { ...basePayload.steps[2]!, order: 2 },
    ]);
    const movedUp = moveStepByOffset(basePayload.steps, 1, -1);
    expect(movedUp).not.toBe(basePayload.steps);
    expect(movedUp).toHaveLength(3);
    expect(movedUp).toEqual([
      { ...basePayload.steps[1]!, order: 1 },
      { ...basePayload.steps[0]!, order: 2 },
      { ...basePayload.steps[2]!, order: 3 },
    ]);
    const movedDown = moveStepByOffset(basePayload.steps, 1, 1);
    expect(movedDown).not.toBe(basePayload.steps);
    expect(movedDown).toHaveLength(3);
    expect(movedDown).toEqual([
      { ...basePayload.steps[0]!, order: 1 },
      { ...basePayload.steps[2]!, order: 2 },
      { ...basePayload.steps[1]!, order: 3 },
    ]);
    expect(moveStepByOffset(basePayload.steps, 0, -1)).toBe(basePayload.steps);
    expect(moveStepByOffset(basePayload.steps, basePayload.steps.length - 1, 1)).toBe(
      basePayload.steps
    );
    expect(moveStepByOffset(basePayload.steps, 99, 1)).toBe(basePayload.steps);
  });
});
