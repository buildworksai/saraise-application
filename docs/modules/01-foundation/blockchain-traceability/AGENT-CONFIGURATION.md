# Agent Configuration: Blockchain Traceability

## AI Agents

The following AI agents are available in this module:

1.  **Traceability Verifier**
    *   **Role**: Verifies the complete chain of custody for a product.
    *   **Capabilities**: Traces product history, checks for gaps in the chain, verifies location consistency.
    *   **Prompt**: "Verify the traceability chain for product [PRODUCT_ID]."

2.  **Authenticity Validator**
    *   **Role**: Validates product authenticity using blockchain records.
    *   **Capabilities**: Checks authenticity tokens against the blockchain, verifies manufacturer signatures.
    *   **Prompt**: "Check if product [PRODUCT_ID] with token [TOKEN] is authentic."

3.  **Compliance Auditor**
    *   **Role**: Audits compliance records against regulations.
    *   **Capabilities**: Reviews compliance logs, verifies blockchain proofs for audit trails.
    *   **Prompt**: "Audit compliance records for batch [BATCH_ID]."

## Workflows

The following workflows are enabled:

1.  **Supply chain traceability workflow**
    *   **Trigger**: Shipment received or product manufactured.
    *   **Steps**: Record event -> Update blockchain -> Notify stakeholders.

2.  **Product authenticity verification workflow**
    *   **Trigger**: Customer scan or retailer check.
    *   **Steps**: Verify token -> Query blockchain -> Return status.

3.  **Compliance audit workflow**
    *   **Trigger**: Scheduled audit or regulatory request.
    *   **Steps**: Gather records -> Verify proofs -> Generate report.

## Ask Amani Configuration

Ask Amani is configured to understand the following intents:

*   "Trace product origin" -> Invokes `Traceability Verifier`
*   "Verify product authenticity" -> Invokes `Authenticity Validator`
*   "Audit compliance records" -> Invokes `Compliance Auditor`
