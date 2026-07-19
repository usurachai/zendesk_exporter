# Agent-Driven GitHub SDLC Workflow

Industry-standard, PR-gated software development lifecycle for autonomous
subagent execution. Designed for the `pi-subagents` orchestration model.

---

## Guiding Principles

| # | Principle | Why |
|---|-----------|-----|
| 1 | **Main is protected** — no direct pushes | Prevents unreviewed code reaching `main` |
| 2 | **Every change goes through a PR** | Traceability + mandatory review gate |
| 3 | **4-eyes rule** — author ≠ reviewer | Catch what the author missed |
| 4 | **Issue = handoff artifact** | Self-contained; any worker can implement from it alone |
| 5 | **Verify before you write** | Free reviewer models produce false positives — confirm claims against real code |
| 6 | **Minimal change** | Smallest correct diff reduces review surface and regression risk |

---

## Branch Strategy

```
main  ──────────────────────────────────────────  (protected, always green)
  ├── fix/issue-NNN-short-desc      (bug fixes)
  ├── feat/issue-NNN-short-desc     (features)
  └── chore/issue-NNN-short-desc    (maintenance)
```

Branch naming: `<type>/issue-<NNN>-<kebab-short-desc>`, branched from `origin/main`.

---

## Workflow Phases

```
┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│ PHASE 0      │ → │ PHASE 1      │ → │ PHASE 2-4    │ → │ PHASE 5      │ → │ PHASE 6      │
│ DISCOVERY    │   │ ISSUE        │   │ IMPL + PR    │   │ REVIEW       │   │ MERGE        │
│ reviewer     │   │ planner      │   │ worker       │   │ reviewer     │   │ reviewer     │
│ (fresh)      │   │ (verify!)    │   │ (branch+fix) │   │ (fresh,diff) │   │ (decision)   │
└──────────────┘   └──────────────┘   └──────────────┘   └──────────────┘   └──────────────┘
```

### Phase 0 — Discovery & Triage
- **Agent:** `reviewer` (fresh context) or `scout`
- **Action:** Scan repo, produce candidate issues with `file:line` references and severity tags.
- **Output:** List of findings. Treat as *candidates*, not facts.

### Phase 1 — Issue Creation (Handoff Artifact) ⚠️ VERIFY FIRST
- **Agent:** `planner` (or `reviewer`)
- **Critical step:** Before writing the issue, **verify every claim against the actual code**.
  The `reviewer` (Nemotron free) has produced false positives in this repo
  (`exporter.py` "unused start_time" — actually used; `logger.py` "duplicate handler" —
  already idempotent). Unverified issues waste worker cycles.
- **Issue must contain** (use `.github/ISSUE_TEMPLATE/agent_handoff.md`):
  - Root cause with `file:line` + code snippet (**verified**)
  - Impact + severity
  - Concrete proposed fix (exact edit if known)
  - Acceptance criteria (checkboxes)
  - Verification steps (commands)
- **Self-contained:** a worker must implement from this alone, no re-analysis.

### Phase 2 — Branch
- **Agent:** `worker`
- **Command:** `git checkout -b fix/issue-NNN-short-desc origin/main`

### Phase 3 — Implementation
- **Agent:** `worker`
- Implement the **minimal** fix described in the issue.
- Run verification **before** committing:
  ```bash
  uv run python -c "import ast,glob; [ast.parse(open(f).read()) for f in glob.glob('src/**/*.py', recursive=True)]"
  uv run python -m pytest tests/
  ```
- Commit: `git commit -m "fix: <summary> (closes #NNN)"`

### Phase 4 — PR Submission
- **Agent:** `worker` (the SAME agent that made the change)
- Push branch, open PR referencing the issue:
  ```bash
  git push origin fix/issue-NNN-short-desc
  gh pr create --base main --head fix/issue-NNN-short-desc \
    --title "fix: <summary> (closes #NNN)" \
    --body "$(cat <<'EOF'
  ## Related Issue
  Closes #NNN

  ## Summary
  <what + why>

  ## Verification
  - Syntax: OK
  - Tests: 62 passed
  EOF
  )"
  ```

### Phase 5 — PR Review (4-eyes, DIFFERENT agent)
- **Agent:** `reviewer` (fresh context, **NOT** the worker)
- Review the diff for correctness, tests, conventions, regressions.
- Decision:
  ```bash
  gh pr review <PR> --approve
  # or
  gh pr review <PR> --request-changes --body "<findings>"
  ```
- If changes requested → worker iterates (back to Phase 3).

### Phase 6 — Merge Decision
- **Agent:** `reviewer` (the one who approved)
- If approved **and** CI is green:
  ```bash
  gh pr merge <PR> --squash --delete-branch
  ```
- Issue auto-closes via `closes #NNN` in commit/PR body.

---

## Enforcement & Constraints

### Branch Protection (recommended)
Requires **GitHub Pro or a public repo**. For this private repo, the API returns
`403 Upgrade to GitHub Pro or make this repository public`. To enable:
```bash
gh api repos/<owner>/<repo>/branches/main/protection --method PUT \
  -F required_status_checks='{"strict":true,"contexts":["test"]}' \
  -F enforce_admins=true \
  -F required_pull_request_reviews='{"dismiss_stale_reviews":true,"required_approving_review_count":1}' \
  -F restrictions=null
```
This enforces: PR required, ≥1 review, `test` status check must pass.

### Until branch protection is available
The policy is enforced by **orchestrator discipline**:
- The parent agent **never pushes to `main` directly**.
- All changes flow through a PR (Phases 2–6).
- CI (`.github/workflows/ci.yml`) runs `test` on every PR to `main`, providing
  the automated gate.

### Reviewer Model Reliability
The `reviewer` agent uses `nvidia/nemotron-3-ultra-550b-a55b:free`. Free models
can hallucinate findings. **Phase 1 verification is mandatory** — never write an
issue from unverified reviewer output.

---

## Agent → Model Mapping (current config)

| Agent | Model | Role in workflow |
|-------|-------|-----------------|
| `reviewer` | Nemotron 3 Ultra (free) | Phase 0 discovery, Phase 5 PR review |
| `planner` | MiMo-V2.5 | Phase 1 issue creation |
| `worker` | MiMo-V2.5 | Phases 2–4 implementation + PR |
| `oracle` | MiMo-V2.5 | Escalation / direction check |
| `scout` | Hy3 (free) | Fast recon |
| `context-builder` | DeepSeek V4 Flash | Context synthesis |
| `researcher` | DeepSeek V4 Flash | External research |
| `delegate` | Hy3 (free) | Lightweight delegation |
