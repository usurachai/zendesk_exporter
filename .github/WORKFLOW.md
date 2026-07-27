# GitHub Workflow — Subagent Instructions (TDD + Cross-Model Review)

This document defines the **mandatory step-by-step workflow** that all subagents must follow.

## Core Principles

1. **Worker does the code. Reviewer does the review. Never both in one agent.**
2. **Worker and reviewer use DIFFERENT LLM models** (cross-model adversarial review).
3. **TDD for code changes**: Tests before implementation for `src/*.py`.
4. **No human blockers**: All routine work merges autonomously.

---

## Workflow Steps

```
FINDING → ISSUE (w/ test plan) → BRANCH → TDD CYCLE → PR → CROSS-MODEL REVIEW → MERGE
```

### Step 1: Finding → GitHub Issue

When a finding is discovered (by scout, oracle, or manual):

1. **Create a GitHub issue** using `gh issue create` with:
   - Clear title with type prefix: `fix:`, `feat:`, `chore:`, `docs:`
   - Description with root cause, file:line references, impact
   - **Testable acceptance criteria** (what tests must pass)
   - **Test plan** (what tests to write and why)
   - Proposed fix approach
   - Risk tier: DT1 (Docs) / DT2 (Config) / T1 (Code) / T2 (New Code) / T3 (Critical)

2. **Issue format** — use `.github/ISSUE_TEMPLATE/agent_handoff.md` structure

### Step 2: Issue → Branch

Create a branch from `origin/main` named:
```
fix/issue-<NNN>-<kebab-short-description>
feat/issue-<NNN>-<kebab-short-description>
chore/issue-<NNN>-<kebab-short-description>
docs/issue-<NNN>-<kebab-short-description>
```

**Never commit directly to `main`.**

### Step 3: TDD Cycle (WORKER ONLY — Model A)

**Only the `worker` subagent makes code changes.** The worker follows TDD for `src/*.py` changes.

#### For Code Changes (`src/*.py`)

```
RED     → Write failing test(s) that capture acceptance criteria
          Test MUST fail initially (proves it tests something)
          Commit: "test: add failing test for <description> (refs #NNN)"

GREEN   → Write minimal code to make tests pass
          No extra features — just enough to pass
          Commit: "feat: implement <description> (fixes #NNN)"
          OR    "fix: <description> (fixes #NNN)"

REFACTOR → Clean up code if needed, tests must still pass
           Commit: "refactor: clean up <description> (refs #NNN)"
```

#### For Other Changes

| Type | Validation |
|------|-----------|
| Docs (`.md`) | Write accurately, reviewer checks |
| Config (`.yaml`) | Ensure defaults load, reviewer checks |
| Scripts (`.sh`) | Run shellcheck, dry-run if possible |

### Step 4: Push + Open PR

Push the branch and create a PR:
```bash
git push -u origin <branch-name>
gh pr create \
  --base main \
  --head <branch-name> \
  --title "<type>: <description> (fixes #<NNN>)" \
  --body "## Description
...
Closes #<NNN>"
```

The PR body must include:
- Description of changes
- Risk tier classification
- Test evidence (commit log showing test before code)
- Reference to the issue: `Closes #<NNN>`

### Step 5: Cross-Model Review (REVIEWER — Model B)

**The reviewer uses a DIFFERENT LLM than the worker.** This is adversarial review.

The reviewer must:

1. **Check TDD compliance**: Verify test commit precedes implementation commit
2. **Read the diff**: `gh pr diff <NNN>` or `git diff main...<branch>`
3. **Run tests**: `uv run python -m pytest tests/ -v`
4. **Check test quality**: Coverage, meaningful assertions, edge cases
5. **Cite evidence**: Every finding must include test output, diff line, or CLI output
6. **Classify risk tier**: DT1, DT2, T1, T2, or T3
7. **Report findings** (saved for PR comment):

```markdown
## Review
- **TDD Compliant**: Yes/No (test commit before code commit)
- **Tests Pass**: Yes/No (pytest output)
- **Correct**: what is already good (with evidence)
- **Issues**: file:line — description (with evidence)
- **Risk Tier**: DT1/DT2/T1/T2/T3
- **Decision**: MERGE / SELF-HEAL
```

8. **Post findings as GitHub PR review**:

```bash
# Build review body from findings above
REVIEW_BODY=$(cat <<'REVIEW'
## Review
- **Risk Tier**: T1
- **TDD Compliant**: Yes
- **Tests Pass**: Yes
- **Correct**: ...
- **Issues**: none
- **Decision**: MERGE
REVIEW
)

# For approval (T1, DT1, DT2 — merge):
gh pr review <NNN> --approve --body "$REVIEW_BODY"

# For changes requested (defects found, self-heal needed):
gh pr review <NNN> --request-changes --body "$REVIEW_BODY"
```

**Why this matters:** Without posting to the PR, reviewer findings are invisible — they live only in ephemeral local artifacts. Posting creates a permanent audit trail on GitHub that anyone can view.

**Reviewer NEVER edits code.** If defects are found, report them for the worker to fix.

### Step 6: T3 Two-Model Consensus (if T3)

For T3 changes (security, auth, credentials):

1. Reviewer-1 (Model B) reviews → PASS/FAIL
2. If PASS, Reviewer-2 (Model C) reviews → PASS/FAIL
3. Both PASS = auto-merge. Either FAIL = self-heal loop.

### Step 7: Self-Healing Loop (if defects found)

```
REVIEWER finds defects → reports with evidence (--request-changes) → WORKER fixes → commits → pushes
  → REVIEWER re-reviews → reports state (--approve or --request-changes) → repeat up to 3 rounds
  → EXHAUSTED → AUTO-CLOSE PR + file new issue for triage
```

**Important:** The reviewer must post a **new** `gh pr review` after each fix round (not just a comment).
The PR must reach `APPROVED` state — a `COMMENTED` review does NOT satisfy the re-review requirement.

If the reviewer cannot self-approve (GitHub blocks self-approval on own PRs), the orchestrator
must inspect the review body and proceed only when the reviewer explicitly states "approved" or "no further issues" —
never skip the re-review step just because GitHub blocks the API call.

### Step 8: Merge (requires APPROVED review)

**PRE-MERGE VERIFICATION (MANDATORY):**

Before merging, verify the review state:
```bash
# Check if LATEST review is APPROVED (sort by submittedAt descending, take first)
LATEST_REVIEW=$(gh pr view <NNN> --json reviews --jq '.reviews | sort_by(.submittedAt) | reverse | .[0].state')

if [ "$LATEST_REVIEW" != "APPROVED" ]; then
  echo "ERROR: Latest review is not APPROVED. Cannot merge."
  echo "Latest review state: $LATEST_REVIEW"
  exit 1
fi
echo "Latest review is APPROVED. Proceeding with merge."
```

| Tier | Action |
|------|--------|
| **DT1, DT2** | Auto-merge after review pass |
| **T1, T2** | Auto-merge after CI + review pass |
| **T3** | Auto-merge after two-model review + CI pass |

**Prerequisite for ALL tiers:** The latest review must be in `APPROVED` state.
- If the reviewer requested changes and the worker fixed them, a **re-review** is required.
- A `COMMENTED` review does NOT satisfy this requirement.
- If GitHub blocks self-approval (same user), the orchestrator must verify the review body explicitly states approval before merging.

**No human gates.** All routine work merges autonomously — but the re-review cycle must complete.

**ENFORCEMENT:**
```bash
# Safe merge command that checks for approval first
LATEST_REVIEW=$(gh pr view <NNN> --json reviews --jq '.reviews | sort_by(.submittedAt) | reverse | .[0].state')
if [ "$LATEST_REVIEW" != "APPROVED" ]; then
  echo "ERROR: Latest review is not APPROVED. Cannot merge."
  echo "Latest review state: $LATEST_REVIEW"
  exit 1
fi
echo "Latest review is APPROVED. Proceeding with merge."
gh pr merge <NNN> --squash --admin
```

---

## Agent Role Assignments

| Role | Agent | Model | Responsibility |
|------|-------|-------|----------------|
| **Discovery** | `scout` | Hy3 (free) | Find issues, gather context |
| **Planning** | `planner` | MiMo-V2.5 | Verify findings, create issue + test plan |
| **Implementation** | `worker` | **Model A** (Claude) | TDD cycle → commit → push → PR |
| **Review** | `reviewer-1` | **Model B** (GPT-4o) | PR review → tier classification |
| **T3 Review** | `reviewer-2` | **Model C** (Gemini) | Second opinion for T3 only |
| **Validation** | `oracle` | MiMo-V2.5 | Decision consistency (escalation only) |

## Rules

1. **Worker never reviews its own PR.** Always delegate to `reviewer`.
2. **Worker and reviewer use DIFFERENT models.** This is adversarial review.
3. **Reviewer never edits code.** Only reads and reports with evidence.
4. **Always branch from `origin/main`.** Never from another feature branch.
5. **Always reference the issue** in commit messages and PRs.
6. **TDD for code**: Test commit must precede implementation commit.
7. **Always run tests** before committing and before approving.
8. **Evidence required**: Every review finding must cite a source artifact.
9. **No human gates**: All routine work merges autonomously.
10. **Self-heal max 3 rounds**: Then auto-close + new issue.
