## Related Issue
Closes #

## Summary
<!-- What changed and why. One paragraph. -->

## Risk Tier
<!-- DT1 (Docs) / DT2 (Config/Scripts) / T1 (Code) / T2 (New Code) / T3 (Critical) -->

## Changes
<!-- Bullet list of concrete changes. -->

## TDD Compliance (for code changes)
<!-- For src/*.py changes only. Skip for docs/config/scripts. -->
- [ ] Test commit precedes implementation commit
- [ ] Tests capture acceptance criteria from issue
- [ ] All tests pass: `uv run python -m pytest tests/ -v`

### Commit Log (TDD evidence)
<!-- Paste the commit log showing test → code → refactor order -->
```
test: add failing test for <description> (refs #NNN)
feat: implement <description> (fixes #NNN)
```

## Verification
- [ ] Syntax check passed (`ast.parse` on all src files)
- [ ] Tests passed (`uv run python -m pytest tests/ -v`)
- [ ] Lint passed (`uv run ruff check src/`)

## Evidence
<!-- Paste the exact commands run and their output (pass/fail). -->

## Reviewer Checklist
- [ ] TDD compliant (test before code for src/*.py)
- [ ] Code follows repo conventions
- [ ] Fix matches the issue's proposed solution
- [ ] No regressions introduced
- [ ] Tests added/updated if behavior changed
- [ ] No silent exception swallowing
- [ ] Evidence provided for all findings (if reviewer)
