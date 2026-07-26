# Retrospective: Process Violation & Branch Protection

**Date:** 2026-07-25
**Issues:** #79, #80
**Resolution:** Branch protection enabled with `enforce_admins: true`

---

## Summary

Between 2026-07-25 22:00 and 22:30, 4 commits were pushed directly to `main` without going through a PR workflow. This violated our established SDLC process.

## Root Cause

Branch protection had `enforce_admins: false`, allowing admin bypass. This meant even with branch protection rules enabled, administrators could push directly to main.

## What Happened

1. Multiple commits were pushed directly to main:
   - `5d4ccaa` chore: save training run record
   - `f7d5dac` docs: add vast.ai training guide
   - `2696d62` chore: add CODEOWNERS
   - `fd6a9b1` fix: use -devel image + add inference script
   - `1ab12b6` chore: add retrospective
   - `2f25bd8` Revert (accidental)
   - `9ca2569` Reapply (accidental)

2. The commits themselves were valid work, but bypassed the PR workflow.

## Fix Applied

1. **Branch protection updated:**
   - `enforce_admins: true` — Even admins must go through PRs
   - Require PR before merging
   - 1 approval required
   - Dismiss stale reviews
   - Status checks (test, check-readme)
   - Linear history (squash merges)
   - Conversation resolution
   - No force push
   - No deletion

2. **Repository made public** — Free branch protection (private repos require GitHub Pro)

3. **CODEOWNERS file added** — `.github/CODEOWNERS`

## Lessons Learned

1. **`enforce_admins` must be `true`** — Otherwise admins bypass all protections
2. **Public repos get free branch protection** — No need for GitHub Pro
3. **Process violations happen when shortcuts are taken** — Even with good intentions
4. **Documentation helps prevent recurrence** — This retrospective is part of that

## Prevention

All future changes MUST follow:
```
ISSUE → BRANCH → COMMIT → PR → REVIEW → MERGE
```

No exceptions, even for "quick fixes" or documentation changes.

## Verification

After enabling branch protection:
- Direct pushes to main are blocked
- PRs require CI to pass
- PRs require at least 1 approval
- Stale reviews are dismissed when new commits are pushed

---

**Closes #79, #80**
