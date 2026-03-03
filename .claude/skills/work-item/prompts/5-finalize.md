# Stage 5: Finalize Work Item #{{ITEM_NUMBER}} — {{ITEM_TITLE}}

You are finalizing the implementation of a work item for the pumpfun-cli project. Commit the changes, create a PR, and update documentation.

## Verification Results

{{VERIFICATION_OUTPUT}}

## Project Root

`/home/antonsauchyk/Documents/pump-fun-projects/pumpfun-cli`

## Steps

### 1. Update docs/work-items.md

Mark item #{{ITEM_NUMBER}} as done. Change the heading from:
```
### N. Title
```
to:
```
### N. ~~Title~~ ✅ Done — PR [#X](URL)
```

The PR URL will be filled in after step 5. For now, use a placeholder `TBD`.

### 2. Update docs/implementation-progress.md

Add a new section for this work item with:
- Task name and status (Done)
- Files modified
- Key details about the implementation
- Number of new tests added

Follow the existing format in the file.

### 3. Stage and commit

Stage only the files that were changed during implementation plus the docs you just updated. Do NOT use `git add -A` or `git add .`.

```bash
git add <each file from FILES_CHANGED> docs/work-items.md docs/implementation-progress.md
git status
```

Verify no `.env`, `wallet.enc`, `idl/`, or credential files are staged.

Commit with conventional commit format:
```bash
git commit -m "feat: <short description of the feature>

Implements work item #{{ITEM_NUMBER}} ({{ITEM_TITLE}}).

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

### 4. Push the feature branch

```bash
git push -u origin HEAD
```

### 5. Create PR

```bash
gh pr create --title "feat: {{ITEM_TITLE}}" --body "$(cat <<'EOF'
## Summary

Implements work item #{{ITEM_NUMBER}} from `docs/work-items.md`.

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

### 6. Update work-items.md with PR link

Now that you have the PR URL, go back and update `docs/work-items.md` to replace the `TBD` placeholder with the actual PR link. Create a second commit (do NOT amend):

```bash
git add docs/work-items.md
git commit -m "docs: add PR link for work item #{{ITEM_NUMBER}}"
git push
```

### 7. Report

Output the PR URL.

## Output Format

## PR Created
**URL:** <PR URL>
**Branch:** <branch name>
**Title:** <PR title>

## Docs Updated
- work-items.md: item #{{ITEM_NUMBER}} marked Done
- implementation-progress.md: section added

## CONSTRAINTS

- Do NOT commit `.env`, `wallet.enc`, or credential files.
- Do NOT push to `main` directly. Always use feature branch + PR.
- Do NOT merge the PR. That is the user's decision.
