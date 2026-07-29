import { UnavailableCapabilityPage } from "../components/CommunicationHubUI";

export function TemplatesPage() {
  return (
    <UnavailableCapabilityPage
      title="Communication templates"
      description="Template governance requires a backend template contract before operators can manage message content."
      limitation="Communication Hub currently exposes only channels, messages, and health endpoints. No template API exists under /api/v1/communication-hub/, so this route stops at a governed unavailable state instead of showing mock template data."
    />
  );
}
