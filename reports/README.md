# reports/

**This is the ONLY permitted location for reports in this repository.** *(Ordnung)*

## REQUIRED here (Kaizen enforcement artifacts)

| Artifact | When |
|----------|------|
| `RETRO_PHASE_{N}.md` | On every phase completion — what worked, what failed, metrics delta, prevention items |
| `TECH_DEBT.md` | Maintained continuously, reviewed every sprint |
| Incident root-cause analyses | After every incident |
| Explicitly requested reports | When the user asks for one |

## FORBIDDEN

- **Unsolicited status, summary, progress, or "COMPLETE"/"FINAL" files.** If it was not
  requested and is not one of the required artifacts above, do not create it.
- **Any report outside this directory** — especially at the repository root. The root is
  not a scratch pad.
- **Completion claims without reproducible evidence.** A document asserting "complete"
  without passing test/build output is itself a violation. *(Jidoka)*

See the root `AGENTS.md` § Documentation & Reporting Standards.
