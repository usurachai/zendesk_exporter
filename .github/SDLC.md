# Agent-Driven GitHub SDLC — Fully Agentic Mode (TDD + Cross-Model Review)

> **Concrete step-by-step instructions for subagents:**
> See [WORKFLOW.md](./WORKFLOW.md) — the mandatory workflow that all subagents must follow.

Fully autonomous development lifecycle with **zero human blockers** for routine
work. All phases — discovery, issue writing, implementation (TDD), PR creation,
and cross-model review — are performed by subagents. Human involvement is
limited to outcome review and exception triage.

---

## Guiding Principles

| # | Principle | Why |
|---|-----------|-----|
| 1 | **Agentic by default** | Subagents run discovery → issue → TDD → PR → review autonomously |
| 2 | **No human blockers** | Humans review outcomes, not gate merges |
| 3 | **Risk = validation depth** | T1/T2/T3 define automated checks, not human permission |
| 4 | **TDD for code** | Tests before implementation for `src/*.py` changes |
| 5 | **Cross-model review** | Reviewer uses different LLM than worker (adversarial) |
| 6 | **Self-healing loops** | Review failures auto-fixed by worker — max 3 rounds |
| 7 | **Evidence-based review** | Every finding must cite test output, diff line, or CLI output |
| 8 | **Minimal change** | Smallest correct diff reduces review surface |

---

## Risk Tiers (drive validation depth)

| Tier | Examples | Automated Validation | Human? |
|------|----------|---------------------|--------|
| **DT1 — Docs** | README, .md files | Reviewer: accuracy, links, formatting | No |
| **DT2 — Config/Scripts** | .yaml, .sh, .yml | Reviewer + lint/dry-run | No |
| **T1 — Code (tested)** | Bug fix in src/*.py with tests | Full TDD + CI + cross-model review | No |
| **T2 — Code (new)** | Feature in src/*.py | Full TDD + CI + cross-model review | No |
| **T3 — Critical** | Security, auth, credentials, data model | Full TDD + CI + **two-model review** | No |

**Key shift:** Risk tiers define how much automated validation occurs, not
whether to ask a human. T3 uses two-model consensus instead of human approval.

---

## Pipeline (fully agentic)

```
TRIGGER (schedule / new finding / manual)
  │
  ├─ PHASE 0  scout     → discover ONE candidate issue          [AUTONOMOUS]
  ├─ PHASE 1  planner   → verify claim + write issue w/ test plan [AUTONOMOUS]
  ├─ PHASE 2  worker    → TDD cycle: RED → GREEN → REFACTOR     [AUTONOMOUS]
  ├─ PHASE 3  worker    → push + open PR (references issue)     [AUTONOMOUS]
  ├─ PHASE 4  reviewer  → cross-model review + tier classify    [AUTONOMOUS]
  │        │
  │        ├─ PASS + T1/T2    → AUTO-MERGE (squash)             [AGENTIC]
  │        ├─ PASS + T3       → reviewer-2 (Model C) → MERGE    [AGENTIC]
  │        └─ FAIL (defects)  → worker auto-fixes → re-review   [SELF-HEAL]
  │                                └─ loop ×3 exhausts → AUTO-CLOSE + NEW ISSUE
  │
  └─ (No human gate — all routine work merges autonomously)
```

---

## TDD Protocol (Phase 2 — Worker)

TDD is enforced for `src/*.py` code changes. Other file types use tiered validation.

### For Code Changes (`src/*.py`)

```
RED     → write failing test that captures acceptance criteria
          Test MUST fail initially (proves it tests something)
          Commit: "test: add failing test for <description> (refs #NNN)"

GREEN   → write minimal code to make tests pass
          No extra features — just enough to pass
          Commit: "feat: implement <description> (fixes #NNN)"
          OR    "fix: <description> (fixes #NNN)"

REFACTOR → clean up code if needed, tests must still pass
           Commit: "refactor: clean up <description> (refs #NNN)"
```

### For Other Changes

| Type | Validation |
|------|-----------|
| Docs (`.md`) | Reviewer checks accuracy, links, formatting |
| Config (`.yaml`) | Config-loader tests (if available) + review |
| Scripts (`.sh`) | Shellcheck lint + dry-run validation |

---

## Cross-Model Review (Phase 4)

The reviewer uses a **different LLM** than the worker for adversarial review.

| Role | Model | When |
|------|-------|------|
| Worker | Model A (e.g., Claude) | Implementation |
| Reviewer-1 | Model B (e.g., GPT-4o) | All PRs |
| Reviewer-2 | Model C (e.g., Gemini) | T3 only |

### Reviewer Requirements

1. **Check TDD compliance**: Test commit must precede implementation commit
2. **Run tests**: `uv run python -m pytest tests/ -v`
3. **Assess test quality**: Coverage, meaningful assertions, edge cases
4. **Cite evidence**: Every finding must include test output, diff line, or CLI output
5. **Classify risk tier**: DT1, DT2, T1, T2, or T3

### T3 Two-Model Consensus

For T3 changes (security, auth, credentials):
1. Reviewer-1 (Model B) reviews → PASS/FAIL
2. If PASS, Reviewer-2 (Model C) reviews → PASS/FAIL
3. Both PASS = auto-merge. Either FAIL = self-heal loop.

---

## Self-Healing Review Loop

On review failure (defects found):

1. Reviewer reports findings with evidence (file:line, test output) via `gh pr review --request-changes`.
2. Worker receives findings, applies minimal fix on the same branch.
3. Worker pushes; PR is updated.
4. Reviewer re-reviews via `gh pr review --approve` or `--request-changes`.
   A `COMMENTED` review does NOT satisfy the re-review requirement.
   Merge requires an `APPROVED` review state.
5. Repeat up to `MAX_REVIEW_ROUNDS` (default **3**).
6. If loop exhausts → **auto-close PR** with diagnosis + **file new issue** for triage.

No human participates in the loop. Exhausted loops create new issues for
manual attention — no PRs hang open indefinitely.

---

## Issue = Handoff Artifact (TDD-Aware)

The Phase 1 issue includes testable acceptance criteria and a test plan.
Use `.github/ISSUE_TEMPLATE/agent_handoff.md`:

- Root cause with `file:line` + code snippet (**verified**)
- **Testable acceptance criteria** (what tests must pass)
- **Test plan** (what tests to write and why)
- Concrete proposed fix
- Risk tier classification

> **Verification is mandatory.** Never write an issue from unverified
> reviewer output. Free models produce false positives.

---

## Agent → Model Mapping

| Agent | Model | Role in workflow |
|-------|-------|-----------------|
| `scout` | Hy3 (free) | Phase 0 discovery |
| `planner` | MiMo-V2.5 | Phase 1 verified issue + test plan |
| `worker` | **Model A** (e.g., Claude) | Phases 2–3: TDD + PR |
| `reviewer-1` | **Model B** (e.g., GPT-4o) | Phase 4: primary review |
| `reviewer-2` | **Model C** (e.g., Gemini) | Phase 4: T3 second review |
| `oracle` | MiMo-V2.5 | Escalation / direction check |
| `context-builder` | DeepSeek V4 Flash | Context synthesis |
| `researcher` | DeepSeek V4 Flash | External research |

---

## Enforcement & Constraints

### Branch Protection (recommended)
Requires **GitHub Pro or a public repo**. For this private repo the API returns
`403`. To enable:
```bash
gh api repos/<owner>/<repo>/branches/main/protection --method PUT \
  -F required_status_checks='{"strict":true,"contexts":["test"]}' \
  -F enforce_admins=true \
  -F required_pull_request_reviews='{"dismiss_stale_reviews":true,"required_approving_review_count":1}' \
  -F restrictions=null
```

### Until branch protection is available
- Policy enforced by **orchestrator discipline** (never push to `main`).
- CI runs `test` on every PR to `main` — automated gate.
- Cross-model review replaces human 4-eyes principle.

### Known constraints
| Constraint | Impact | Handling |
|-----------|--------|----------|
| Single GitHub account | Cannot enforce true 4-eyes | Cross-model review substitutes |
| Branch protection needs Pro/public | No enforced review gate | CI gate + agent discipline |
| Free models hallucinate | False review findings | Evidence requirement + self-heal |
| TDD not enforced by CI | Worker could skip RED phase | Reviewer checks commit order |
