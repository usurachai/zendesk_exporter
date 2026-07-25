# Repository Instructions — zendesk_exporter

## Mandatory GitHub Workflow

All code changes MUST follow this workflow — read `.github/WORKFLOW.md` for the full step-by-step:

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
| PR Review | `reviewer-1` | **Model B** | Review diff → check TDD → classify tier |
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
