# Email Marketing Frontend

Production UI for the governed `/api/v2/email-marketing/` runtime.

The module owns campaigns, versioned templates, audience and delivery evidence,
suppressions, and append-only consent history. `contracts.ts` is the public type,
endpoint, and route source of truth; the service rejects malformed envelopes and
never converts missing data into empty success.

Routes are declared in `routes.ts` and discovered by the tenant route registry.
The five sidebar leaves are Campaigns, Templates, Delivery, Suppressions, and
Consents. Create, detail, and edit pages are contextual children.

Verification:

```bash
npx tsc --noEmit -p src/modules/email_marketing/tsconfig.json
npx eslint src/modules/email_marketing --ext .ts,.tsx --max-warnings 0
npx vitest run src/modules/email_marketing
```
