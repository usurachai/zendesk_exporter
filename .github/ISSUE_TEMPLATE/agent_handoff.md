---
name: Agent Handoff Issue
about: Self-contained bug/feature spec for subagent implementation
title: "[fix/feat/chore]: <short description>"
labels: [triage]
assignees: ""
---

> This issue is the **handoff artifact** for an autonomous subagent.
> It MUST be self-contained: any worker agent should be able to implement
> the fix using ONLY the information below, without re-analysis.

## Summary
<!-- One-line description of the problem or request. -->

## Root Cause (VERIFIED)
<!-- File:line with a code snippet. The claim MUST be verified against the
     actual code before writing this issue. Do not copy reviewer output
     blindly — free models produce false positives. -->
- File: `path/to/file.py:LINENUM`
- Snippet:
  ```python
  # the problematic code
  ```
- Why it is wrong / what breaks:

## Impact
<!-- Who/what is affected. Severity: blocker / warning / nit. -->

## Proposed Fix
<!-- Concrete, minimal change. Include the exact edit if known. -->
```python
# before
# after
```

## Acceptance Criteria
- [ ] Criterion 1
- [ ] Criterion 2

## Verification Steps
<!-- Commands the worker must run BEFORE committing. -->
```bash
uv run python -m pytest tests/
```

## Notes / Constraints
<!-- Non-goals, things to avoid, related issues. -->
