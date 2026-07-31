import type { CrmConfigurationWrite } from "../contracts";

export type DraftError = Readonly<Record<string, string>>;

// The validation rules intentionally mirror independent governed CRM configuration constraints.
// eslint-disable-next-line complexity
export function validateCrmConfigurationDraft(draft: CrmConfigurationWrite): DraftError {
  const errors: Record<string, string> = {};
  const d = draft.document;
  if (!draft.environment.trim()) errors.environment = "Environment is required.";
  if (draft.rollout.percentage < 0 || draft.rollout.percentage > 100)
    errors.rollout = "Rollout must be between 0 and 100 percent.";
  if (d.lead.score_min >= d.lead.score_max)
    errors["lead.score_min"] = "Minimum score must be lower than maximum score.";
  const thresholds = d.lead.grade_thresholds;
  if (!(thresholds.A > thresholds.B && thresholds.B > thresholds.C && thresholds.C >= thresholds.D))
    errors["lead.grade_thresholds"] = "Grade thresholds must descend from A through D.";
  if (d.opportunity.probability_min >= d.opportunity.probability_max)
    errors["opportunity.probability_min"] =
      "Minimum probability must be lower than maximum probability.";
  if (Number(d.opportunity.minimum_amount) <= 0)
    errors["opportunity.minimum_amount"] = "Minimum amount must be positive.";
  if (
    d.forecast.minimum_period_days > d.forecast.default_period_days ||
    d.forecast.default_period_days > d.forecast.maximum_period_days
  )
    errors["forecast.default_period_days"] =
      "Default forecast period must be within configured limits.";
  if (
    d.pagination.default_page_size < 1 ||
    d.pagination.default_page_size > d.pagination.maximum_page_size
  )
    errors["pagination.default_page_size"] =
      "Default page size must be within the configured maximum.";
  if (d.ui.pipeline_fetch_limit < 1 || d.ui.pipeline_fetch_limit > d.pagination.maximum_page_size)
    errors["ui.pipeline_fetch_limit"] =
      "Pipeline fetch limit must be within the API pagination maximum.";
  if (!d.opportunity.stages.length)
    errors["opportunity.stages"] = "At least one pipeline stage is required.";
  return errors;
}
