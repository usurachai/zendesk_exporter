# GitHub Workflow — Subagent Instructions

This document defines the **mandatory step-by-step workflow** that all subagents must follow when doing GitHub-related work in this repository.

## Core Principle

**Worker does the code. Reviewer does the review. Never both in one agent.**

---

## Workflow Steps

```
FINDING → GITHUB ISSUE → BRANCH → WORKER CODE → COMMIT → PR → REVIEWER REVIEW → MERGE
```

### Step 1: Finding → GitHub Issue

When a finding is discovered (by scout, oracle, or manual):

1. **Create a GitHub issue** using `gh issue create` with:
   - Clear title with severity prefix: `HIGH:`, `MEDIUM:`, `LOW:`, `INFO:`
   - Description with root cause, file:line references, impact
   - Proposed fix approach
   - Acceptance criteria (checkboxes)
   - Verification steps
   - Risk tier: T1 (Safe) / T2 (Notable) / T3 (Critical)

2. **Issue format** — use `.github/ISSUE_TEMPLATE/agent_handoff.md` structure:
   ```
   ## Description
   ## Root Cause
   ## Impact
   ## Proposed Fix
   ## Risk Tier
   ## Acceptance Criteria
   - [ ] ...
   ## Verification Steps
   ```

### Step 2: Issue → Branch

Create a branch from `origin/main` named:
```
fix/issue-<NNN>-<kebab-short-description>
```
or
```
feat/issue-<NNN>-<kebab-short-description>
```
or
```
chore/issue-<NNN>-<kebab-short-description>
```

**Never commit directly to `main`.**

### Step 3: Code Changes (WORKER ONLY)

**Only the `worker` subagent makes code changes.** The worker must:

1. Read the GitHub issue for full context
2. Read the relevant source files
3. Apply the minimal correct change
4. Verify with tests: `uv run python -m pytest tests/ -v`

### Step 4: Commit

Commit with a descriptive message referencing the issue:
```
git add <files>
git commit -m "<type>: <description> (fixes #<NNN>)"
git push -u origin <branch-name>
```

### Step 5: Open PR

Create a PR using `gh pr create`:
```
gh pr create \
  --base main \
  --head <branch-name> \
  --title "<type>: <description> (fixes #<NNN>)" \
  --body "## Description\n...\nCloses #<NNN>"
```

The PR body must include:
- Description of changes
- Risk tier classification
- Verification steps
- Reference to the issue: `Closes #<NNN>`

### Step 6: PR Review (REVIEWER ONLY)

**Only the `reviewer` subagent reviews PRs.** The reviewer must:

1. Read the diff: `gh pr diff <NNN>` or `git diff main...<branch>`
2. Read the relevant source files
3. Verify each acceptance criterion from the issue
4. Run tests: `uv run python -m pytest tests/ -v`
5. Classify the risk tier (T1/T2/T3)
6. Report findings:

```
## Review
- Correct: what is already good (with evidence)
- Fixed: issue, location, and resolution (if fix applied)
- Blocker: critical issue that must be resolved before proceeding
- Note: observation, risk, or follow-up item
```

**Reviewer NEVER edits code.** If defects are found, report them for the worker to fix.

### Step 7: Self-Healing Loop (if defects found)

```
REVIEWER finds defects → reports to worker → WORKER fixes → commits → pushes
  → REVIEWER re-reviews → repeat up to 3 rounds → ESCALATE to human
```

### Step 8: Merge

| Tier | Action |
|------|--------|
| **T1 — Safe** | Auto-merge after CI + review pass |
| **T2 — Notable** | Pause → notify human → human approves merge |
| **T3 — Critical** | Pause → notify human → human must review + approve |

---

## Agent Role Assignments

| Role | Agent | Responsibility |
|------|-------|---------------|
| **Discovery** | `scout` | Find issues, gather context |
| **Planning** | `planner` | Verify findings, create issue, plan fix |
| **Implementation** | `worker` | Branch → code → commit → push → PR |
| **Review** | `reviewer` | PR review → tier classification → report |
| **Validation** | `oracle` | Decision consistency check (escalation only) |
| **Merge** | Human | Approve T2/T3 merges |

## Rules

1. **Worker never reviews its own PR.** Always delegate to `reviewer`.
2. **Reviewer never edits code.** Only reads and reports.
3. **Always branch from `origin/main`.** Never from another feature branch.
4. **Always reference the issue** in commit messages and PRs.
5. **Always run tests** before committing and before approving.
6. **T1 merges are automatic** after CI + review pass. T2/T3 need human.
7. **Self-heal up to 3 rounds** then escalate to human.
8. **PR description must be self-contained** — another agent should understand it without reading the issue.