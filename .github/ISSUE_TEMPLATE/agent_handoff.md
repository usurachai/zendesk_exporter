---
name: Agent Handoff Issue
about: Self-contained bug/feature spec for subagent implementation (TDD-aware)
title: "[fix/feat/chore/docs]: <short description>"
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

## Risk Tier
<!-- DT1 (Docs) / DT2 (Config/Scripts) / T1 (Code with tests) / T2 (New code) / T3 (Critical) -->
- Tier: `T1`
- Reason: <!-- why this tier -->

## Testable Acceptance Criteria
<!-- What tests must pass for this issue to be considered done? -->
- [ ] `test_module.py::test_case_1` passes
- [ ] `test_module.py::test_case_2` passes
- [ ] No existing tests break (`uv run python -m pytest tests/ -v`)

## Test Plan
<!-- What tests must the worker write BEFORE implementation? -->
<!-- For docs/config/scripts, describe validation approach instead. -->
- [ ] `test_foo.py::test_bar` — verifies <behavior>
- [ ] `test_foo.py::test_edge_case` — covers <edge case>

## Proposed Fix
<!-- Concrete, minimal change. Include the exact edit if known. -->
```python
# before
# after
```

## Verification Steps
<!-- Commands the worker must run BEFORE committing. -->
```bash
uv run python -m pytest tests/ -v
```

## Notes / Constraints
<!-- Non-goals, things to avoid, related issues. -->
