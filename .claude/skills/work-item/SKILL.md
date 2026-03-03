---
name: work-item
description: Work item pipeline for pumpfun-cli — investigate, plan, implement (TDD), verify, finalize as PR. MUST use this skill whenever the user wants to start, tackle, pick up, implement, or work on a work item from docs/work-items.md. Triggers on any mention of work items by number ("item 5", "item #5", "#5"), by name ("pre-trade balance validation", "quote command", "health check"), or by sequence ("next work item", "next item on the board", "next undone item", "next P1 item", "whatever is next"). Also triggers on phrases like "let's work on", "start implementing", "tackle item", "knock out", "pick up", "can we do item" when referring to the work items board. Does NOT trigger for: running tests, reviewing PRs, listing remaining items, fixing bugs, or explaining code.
---

# Work Item Pipeline

Automate work item execution from `docs/work-items.md` through a 5-stage gated pipeline.

## Invocation

`/work-item <number>` or `/work-item` (picks next undone item).

## Step 0: Resolve the Target Item

1. Read `docs/work-items.md`
2. If a number was provided, find the item with that number (e.g., `### 5.` or `### #5`)
3. If no number was provided, find the lowest-numbered item NOT marked with `~~` strikethrough or `✅ Done`, following the "Recommended Implementation Order" section
4. Extract:
   - `ITEM_NUMBER`: the item number
   - `ITEM_TITLE`: the short title (e.g., "Pre-trade balance validation")
   - `ITEM_DESCRIPTION`: the full text of the item (Source, Problem, Proposed, Scope)
5. Announce: "Starting pipeline for **#N: TITLE**"

## Stage 1: Investigate

1. Read the prompt file: `.claude/skills/work-item/prompts/1-investigate.md`
2. Replace `{{ITEM_NUMBER}}` and `{{ITEM_DESCRIPTION}}` with the values from Step 0
3. Dispatch a subagent:
   ```
   Agent tool:
     subagent_type: general-purpose
     prompt: <filled prompt text>
     description: "Investigate work item #N"
   ```
4. Store the returned output as `INVESTIGATION_OUTPUT`
5. Present the output to the user
6. **GATE:** Ask the user: **proceed** to Stage 2, **re-run** Stage 1, or **abort**?

**If investigation recommends combining items:** Pause and ask the user whether to combine before proceeding. If yes, update `ITEM_DESCRIPTION` to include both items.

## Stage 2: Plan

1. Read the prompt file: `.claude/skills/work-item/prompts/2-plan.md`
2. Replace `{{ITEM_NUMBER}}`, `{{ITEM_DESCRIPTION}}`, and `{{INVESTIGATION_OUTPUT}}`
3. Dispatch a subagent:
   ```
   Agent tool:
     subagent_type: general-purpose
     prompt: <filled prompt text>
     description: "Plan work item #N"
   ```
4. Store the returned output as `PLAN_OUTPUT`
5. Extract `TEST_TIERS` from the "## Test Tiers" section of the plan output
6. Present the output to the user
7. **GATE:** Ask the user: **proceed** to Stage 3, **re-run** Stage 2, or **abort**?

## Stage 3: Implement

1. Read the prompt file: `.claude/skills/work-item/prompts/3-implement.md`
2. Replace `{{ITEM_NUMBER}}`, `{{ITEM_DESCRIPTION}}`, and `{{PLAN_OUTPUT}}`
3. Dispatch a subagent:
   ```
   Agent tool:
     subagent_type: general-purpose
     prompt: <filled prompt text>
     description: "Implement work item #N"
   ```
4. Store the returned output as `IMPLEMENT_OUTPUT`
5. Extract `FILES_CHANGED` and `TEST_COUNT_AFTER` from the output
6. Extract `TEST_COUNT_BEFORE` from the investigation output's "## Baseline Test Count" section
7. Present the output to the user
8. **GATE:** Ask the user: **proceed** to Stage 4, **re-run** Stage 3, or **abort**?

**If subagent reports blockers (cannot get tests green):** Present blockers to user. Options: re-run with adjusted approach, abort, or user intervenes manually.

## Stage 4: Verify

1. Read the prompt file: `.claude/skills/work-item/prompts/4-verify.md`
2. Replace `{{ITEM_NUMBER}}`, `{{ITEM_DESCRIPTION}}`, `{{FILES_CHANGED}}`, `{{TEST_TIERS}}`, `{{TEST_COUNT_BEFORE}}`, and `{{TEST_COUNT_AFTER}}`
3. Dispatch a subagent:
   ```
   Agent tool:
     subagent_type: general-purpose
     prompt: <filled prompt text>
     description: "Verify work item #N"
   ```
4. Store the returned output as `VERIFICATION_OUTPUT`
5. Present the output to the user
6. **GATE:** Ask the user: **proceed** to Stage 5, **re-run** Stage 4, **loop back to Stage 3** (if regressions found), or **abort**?

## Stage 5: Finalize

1. Read the prompt file: `.claude/skills/work-item/prompts/5-finalize.md`
2. Replace `{{ITEM_NUMBER}}`, `{{ITEM_TITLE}}`, and `{{VERIFICATION_OUTPUT}}`
3. Dispatch a subagent:
   ```
   Agent tool:
     subagent_type: general-purpose
     prompt: <filled prompt text>
     description: "Finalize work item #N"
   ```
4. Present the PR URL to the user
5. Pipeline complete. Suggest: "Code review can be done manually or via a code review skill."

## Variables Carried Across Stages

| Variable | Set in | Used in |
|----------|--------|---------|
| `ITEM_NUMBER` | Step 0 | All stages |
| `ITEM_TITLE` | Step 0 | Stage 5 |
| `ITEM_DESCRIPTION` | Step 0 | Stages 1-4 |
| `INVESTIGATION_OUTPUT` | Stage 1 | Stage 2 |
| `TEST_COUNT_BEFORE` | Stage 1 (Baseline Test Count section) | Stage 4 |
| `PLAN_OUTPUT` | Stage 2 | Stage 3 |
| `TEST_TIERS` | Stage 2 (Test Tiers section) | Stage 4 |
| `FILES_CHANGED` | Stage 3 | Stage 4 |
| `TEST_COUNT_AFTER` | Stage 3 | Stage 4 |
| `VERIFICATION_OUTPUT` | Stage 4 | Stage 5 |

## Failure Modes

| Failure | Response |
|---------|----------|
| Item not found in work-items.md | Report error, list available undone items |
| Item already marked Done | Report it's done, ask user to pick another |
| Stage 1 finds item not feasible | Present findings, recommend abort |
| Stage 3 cannot get tests green | Present blockers after 2 attempts, offer re-run/abort/manual |
| Stage 4 finds regressions | Loop back to Stage 3 with failure details |
| Any subagent errors/times out | Report error, offer re-run or abort |
