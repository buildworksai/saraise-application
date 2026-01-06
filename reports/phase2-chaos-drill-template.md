# Phase 2 Chaos Drill Template — Post-Mortem

## Drill: [Scenario Name]
**Date:** [YYYY-MM-DD]  
**Duration:** [start time] – [end time]  
**Owner:** [name/team]

---

## Setup
- Services involved: [list]
- Simulated failure: [brief description]
- Trigger method: [e.g., stop Redis, kill process, iptables rule, etc.]

---

## Observations
- **Time to detect (alert firing):** [HH:MM:SS]
- **Time to mitigation (manual or automatic):** [HH:MM:SS]
- **Impact:** [affected tenants, request failures, etc.]
- **Metrics/signals:** [what changed; cite dashboard or logs]
- **On-call response:** [did runbook execute? issues encountered?]

---

## Findings
- [Finding 1: description, severity (critical/high/medium/low), impact]
- [Finding 2: ...]

---

## Root Causes
- [Cause 1: description, probability assessment]
- [Cause 2: ...]

---

## Fixes & Follow-ups
- [Fix 1: description, assigned to, target completion date]
- [Fix 2: ...]

---

## Validation
- Re-run drill after fixes: [date/time, outcome]

---

## Lessons Learned
- [Lesson 1: what we learned and how to prevent recurrence]
- [Lesson 2: ...]
