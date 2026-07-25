# Repository Instructions — zendesk_exporter

## ⚠️ Pre-Flight Checklist (READ BEFORE ANY CHANGE)

Before writing a single line of code, verify EVERY item on this checklist.
Failure to follow this order has caused workflow violations in the past.

- [ ] **ISSUE FIRST**: Have I created a GitHub issue describing the change?
      If no → STOP. Create the issue. No code without an issue.
- [ ] **BRANCH**: Am I on a branch from `origin/main` (not `main` itself)?
      If no → STOP. Create the branch. Never commit to main.
- [ ] **ISSUE REF**: Does every commit reference the issue (`fixes #NNN`)?
      If no → STOP. Add the reference.
- [ ] **TDD**: For `src/*.py` changes — did I write the test BEFORE the code?
      If no → Revert. Write the failing test first (RED phase).
- [ ] **TESTS PASS**: Have I run `uv run python -m pytest tests/ -v`?
      If no → STOP. Run tests. Fix any failures.
- [ ] **REVIEW**: Have I delegated the PR to `reviewer` (not reviewing my own)?
      If no → STOP. Worker never reviews its own PR.
- [ ] **AUDIT TRAIL**: Has the reviewer posted findings on the PR as a GitHub review comment?
      If no → The review is invisible. Reviewer must use `gh pr review`.
- [ ] **RE-REVIEW**: After fixing reviewer findings, did the reviewer re-approve?
      If no → STOP. Run the review cycle again. Merge requires an APPROVED review.
      A `COMMENTED` review does not satisfy this requirement. If GitHub blocks
      self-approval, verify the review body explicitly states approval before merging.

> **Why this checklist exists:** Previous violations occurred where code was
> changed without an issue, branch, or review. This checklist is the
> process-level guardrail. Treat it as mandatory reading before every action.

## Mandatory GitHub Workflow

Once the pre-flight checklist passes, follow this workflow — read `.github/WORKFLOW.md` for the full step-by-step:

```
FINDING → ISSUE (w/ test plan) → BRANCH → TDD CYCLE → PR → CROSS-MODEL REVIEW → MERGE
```

### Key Rules
1. **Worker does the code. Reviewer does the review.** Never both in one agent.
2. **Worker and reviewer use DIFFERENT LLM models** (cross-model adversarial review).
3. **Never commit to `main`.** Always branch from `origin/main`.
4. **Always reference the GitHub issue** in commits (`fixes #NNN`) and PRs (`Closes #NNN`).
5. **TDD for code changes**: Write tests BEFORE implementation for `src/*.py`.
6. **No human blockers**: All routine work merges autonomously.
7. **Evidence-based review**: Every finding must cite test output, diff line, or CLI output.

### Agent Roles
| Role | Agent | Model | What they do |
|------|-------|-------|-------------|
| Implementation | `worker` | **Model A** | TDD cycle → commit → push → PR |
| PR Review | `reviewer-1` | **Model B** | Review diff → check TDD → classify tier → post to PR |
| T3 Review | `reviewer-2` | **Model C** | Second opinion for critical changes |

### Risk Tiers (validation depth, not human permission)
| Tier | Examples | Validation |
|------|----------|-----------|
| DT1 | Docs (.md) | Review only |
| DT2 | Config/Scripts (.yaml, .sh) | Review + lint |
| T1 | Code fix with tests | TDD + CI + cross-model review |
| T2 | New feature with tests | TDD + CI + cross-model review |
| T3 | Security, auth, credentials | TDD + CI + **two-model review** |

### Quick Commands
```bash
uv run python -m pytest tests/ -v    # Run 63 tests
uv run python run_prepare.py --analyze  # Analyze sentence frequencies
gh pr create --base main --head <branch> --title "..." --body "..."
```

Read `.github/WORKFLOW.md` and `.github/SDLC.md` for complete details before starting any GitHub-related work.
