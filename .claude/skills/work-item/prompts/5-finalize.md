# Stage 5: Finalize Work Item #{{ITEM_NUMBER}} — {{ITEM_TITLE}}

You are finalizing the implementation of a work item for the pumpfun-cli project. Commit the changes and create a PR.

## Verification Results

{{VERIFICATION_OUTPUT}}

## Project Root

`/home/antonsauchyk/Documents/pump-fun-projects/pumpfun-cli`

## Steps

### 1. Stage and commit

Stage only the files that were changed during implementation. Do NOT use `git add -A` or `git add .`. Do NOT stage files in `docs/` or `idl/`.

```bash
git add <each file from FILES_CHANGED>
git status
```

Verify no `.env`, `wallet.enc`, `idl/`, `docs/`, or credential files are staged.

Commit with conventional commit format:
```bash
git commit -m "fix: <short description>

<2-3 sentence explanation of what was done and why>

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

### 2. Push the feature branch

```bash
git push -u origin HEAD
```

### 3. Create PR

The PR description must be **self-contained** — a reviewer should understand the full context without needing to read any external files. Do NOT reference `docs/backlog.md`, `docs/work-items.md`, or any other local documentation files in the PR title or body.

```bash
gh pr create --title "fix: {{ITEM_TITLE}}" --body "$(cat <<'EOF'
## Summary

<Explain the problem that existed and why it matters — a reviewer unfamiliar with the backlog should understand the context from this section alone.>

<1-3 bullet points describing what was added/changed>

## Layers Touched

- `commands/` — <what changed>
- `core/` — <what changed>
- `protocol/` — <what changed>

## Does this affect transaction construction or signing?

<yes/no — explain if yes>

## Test Plan

- Unit tests: <N new tests added, all passing>
- Surfpool: <tested / not needed>
- Mainnet: <tested / not needed>

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

### 4. Report

Output the PR URL.

## Output Format

## PR Created
**URL:** <PR URL>
**Branch:** <branch name>
**Title:** <PR title>

## CONSTRAINTS

- Do NOT commit `.env`, `wallet.enc`, or credential files.
- Do NOT stage or commit files in `docs/` or `idl/`.
- Do NOT push to `main` directly. Always use feature branch + PR.
- Do NOT merge the PR. That is the user's decision.
- Do NOT reference local .md files (backlog, work-items, etc.) in the PR description. The PR must be self-contained.
