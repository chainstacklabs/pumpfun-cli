# E2E Test Report Template

This is the single source of truth for the output format of e2e QA runs.
Write results to `docs/e2e-test-results.md` using this structure.

---

```markdown
# E2E Test Results — <DATE>

## Test Environment
- Wallet: <PUBKEY>
- RPC: <PROVIDER>
- Starting balance: <SOL>
- Ending balance: <SOL>

## Results by Group
| # | Group | Command | Result | Notes |
|---|-------|---------|--------|-------|
| 1 | Wallet | `wallet show` | PASS | |
| 1 | Wallet | `wallet balance` | PASS | |
| ... | ... | ... | ... | ... |

## Issues Found
### <ISSUE-ID>: <Title>
**Severity:** Critical / High / Medium / Low
**Symptom:** What happened
**Reproduction:** Exact commands to reproduce
**Evidence:** Error output, tx signatures, exit codes

## Comparison with Previous Run
Note any issues that are now fixed or new issues that appeared compared to
the last run documented in `docs/e2e-test-results.md`.
```
