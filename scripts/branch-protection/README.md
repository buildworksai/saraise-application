# Branch Protection Payloads

This folder holds JSON payloads for enforcing branch protection on Tier-0 repositories via the GitHub API. The payloads enable PR-required merges, CODEOWNERS approval, enforced admins, and required status checks (`guardrails`, `lint`, `tests`). Use with:

```
gh api --method PUT repos/<owner>/<repo>/branches/main/protection --input scripts/branch-protection/<repo>.json
```

Ownership: platform governance.
