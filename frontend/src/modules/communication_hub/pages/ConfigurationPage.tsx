import { UnavailableCapabilityPage } from "../components/CommunicationHubUI";

export function ConfigurationPage() {
  return (
    <UnavailableCapabilityPage
      title="Communication configuration"
      description="Configuration needs an audited server-side contract before tenant operators can change Communication Hub behavior."
      limitation="Communication Hub currently has no configuration read, preview, version, import, export, or rollback endpoints. This page documents that backend limitation explicitly and does not persist or simulate configuration locally."
    />
  );
}
