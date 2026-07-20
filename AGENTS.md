# Repository Instructions — zendesk_exporter

## Mandatory GitHub Workflow

All code changes MUST follow this workflow — read `.github/WORKFLOW.md` for the full step-by-step:

```
FINDING → GITHUB ISSUE → BRANCH → WORKER CODE → COMMIT → PR → REVIEWER REVIEW → MERGE
```

### Key Rules
1. **Worker does the code. Reviewer does the review.** Never both in one agent.
2. **Never commit to `main`.** Always branch from `origin/main`.
3. **Always reference the GitHub issue** in commits (`fixes #NNN`) and PRs (`Closes #NNN`).
4. **Always run tests** before committing: `uv run python -m pytest tests/ -v`
5. **T1 auto-merges after CI + review. T2/T3 need human approval.**

### Agent Roles
| Role | Agent | What they do |
|------|-------|-------------|
| Implementation | `worker` | Branch → code → commit → push → PR |
| PR Review | `reviewer` | Review diff → classify risk tier → report |

### Quick Commands
```bash
uv run python -m pytest tests/ -v    # Run 63 tests
uv run python run_prepare.py --analyze  # Analyze sentence frequencies
gh pr create --base main --head <branch> --title "..." --body "..."
```

Read `.github/WORKFLOW.md` and `.github/SDLC.md` for complete details before starting any GitHub-related work.
