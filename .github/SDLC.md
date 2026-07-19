# Agent-Driven GitHub SDLC — Fully Agentic Mode

Autonomous software development lifecycle with **human-in-the-loop only for
important actions** (risky merges, security/critical changes, or when an agent
is genuinely blocked). All routine work — discovery, issue writing,
implementation, PR creation, and review — is performed by subagents with **zero
human interaction**.

---

## Guiding Principles

| # | Principle | Why |
|---|-----------|-----|
| 1 | **Agentic by default** | Subagents run discovery → issue → fix → PR → review autonomously |
| 2 | **Human only at decision gates** | Humans appear solely for important actions (T2/T3 merge, blocks) |
| 3 | **Risk-based gating** | T1 auto-merges; T2/T3 require human approval |
| 4 | **Self-healing loops** | Review failures are auto-fixed by the worker — no human |
| 5 | **Silent progress / loud blockers** | No routine pings; escalate only on gate or block |
| 6 | **Verify before write** | Phase 1 verifies reviewer claims (free models hallucinate) |
| 7 | **Minimal change** | Smallest correct diff reduces review surface |

---

## Risk Tiers (drive the human gate)

| Tier | Examples | Agent behavior | Human? |
|------|----------|----------------|--------|
| **T1 — Safe** | Bug fix, test, doc, lint, internal refactor (tests green, no security touch) | Auto-merge after CI + review pass | **Notified only** |
| **T2 — Notable** | New feature, config change, dependency bump, API change | Open PR + pause + concise summary | **Yes — approve merge** |
| **T3 — Critical** | Security, auth, credentials, data model, deletion, architecture | Open PR + pause + full context | **Yes — must review** |

The **reviewer** classifies the tier from the diff (paths touched, keywords,
test impact, security-relevant patterns).

---

## Pipeline (autonomy-annotated)

```
TRIGGER (schedule / new finding / manual)
  │
  ├─ PHASE 0  scout     → discover ONE candidate issue          [AUTONOMOUS]
  ├─ PHASE 1  planner   → verify claim + write self-contained issue [AUTONOMOUS]
  ├─ PHASE 2  worker    → branch + implement + verify (tests)   [AUTONOMOUS]
  ├─ PHASE 3  worker    → push + open PR (references issue)     [AUTONOMOUS]
  ├─ PHASE 4  reviewer  → auto-review + classify risk tier      [AUTONOMOUS]
  │        │
  │        ├─ PASS + T1       → AUTO-MERGE (agentic)            [AGENTIC]
  │        ├─ PASS + T2/T3     → PAUSE → notify human            [HUMAN GATE]
  │        └─ FAIL (defects)   → worker auto-fixes → re-review   [SELF-HEAL]
  │                                └─ loop ×N exhausts → ESCALATE [HUMAN]
  │
  └─ PHASE 5  human     → approve T2/T3 merge                  [HUMAN GATE]
```

**Key shift from manual mode:** Phases 0–4 execute with no human in the loop.
The human is contacted only at Phase 5 (risky merges) or on escalation.

---

## Self-Healing Review Loop

On review failure (defects found, not an architecture blocker):

1. Reviewer reports findings (file:line, severity).
2. Worker receives findings, applies minimal fix on the same branch.
3. Worker pushes; PR is updated.
4. Reviewer re-reviews.
5. Repeat up to `MAX_REVIEW_ROUNDS` (default **3**).
6. If the loop exhausts → **escalate to human** with full context.

No human participates in the loop. The human sees only the final merged
result or an escalation.

---

## Human Gates (the only places humans appear)

| # | Gate | When | Human action |
|---|------|------|--------------|
| 1 | **Risky merge** | T2/T3 PR passes review | Approve / deny (one click) |
| 2 | **Blocked agent** | Worker needs a decision it cannot make | Answer one question |
| 3 | **Loop exhausted** | Review fails `MAX_REVIEW_ROUNDS` times | Triage or intervene |

Routine T1 fixes merge themselves. The human never sees step-by-step
progress — only a quiet "merged #24" note or a "needs your approval: #25" ping.

---

## Triggers

| Trigger | Mechanism | Notes |
|---------|-----------|-------|
| **Scheduled (nightly)** | Chain `nightly-triage` via cron or `subagent schedule` | Fully autonomous discovery + fix |
| **New finding** | Reviewer / scout output | Orchestrator launches the chain |
| **Manual** | `/run-chain nightly-triage` | On-demand |

### Nightly schedule

The `nightly-triage` chain (`.pi/chains/nightly-triage.chain.json`) runs:
`scout → planner → worker → reviewer`.

Enable scheduling in `~/.pi/agent/extensions/subagent/config.json`:
```json
{ "scheduledRuns": { "enabled": true } }
```

Activate a deferred one-off run:
```
subagent({ action: "schedule",
  chain: [ {agent:"scout",...}, {agent:"planner",...}, {agent:"worker",...}, {agent:"reviewer",...} ],
  schedule: "+1d" })
```

For **true nightly recurrence**, wrap in an external cron job (native scheduling
is one-shot):
```
0 2 * * *  cd /path/to/repo && pi run-chain nightly-triage
```

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

## Issue = Handoff Artifact

The Phase 1 issue is **self-contained** so any worker can implement from it
alone (no re-analysis). Use `.github/ISSUE_TEMPLATE/agent_handoff.md`:

- Root cause with `file:line` + code snippet (**verified**)
- Impact + severity
- Concrete proposed fix (exact edit if known)
- Acceptance criteria (checkboxes)
- Verification steps (commands)

> **Verification is mandatory.** The `reviewer` (Nemotron free) has produced
> false positives in this repo (`exporter.py` "unused start_time" — actually
> used; `logger.py` "duplicate handler" — already idempotent). Never write an
> issue from unverified reviewer output.

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
Enforces: PR required, ≥1 review, `test` status check must pass.

### Until branch protection is available
- The policy is enforced by **orchestrator discipline** (never push to `main`).
- CI (`.github/workflows/ci.yml`) runs `test` on every PR to `main` — automated gate.
- The **risk-tier policy** substitutes for 4-eyes: T1 auto-merges, T2/T3 require human.

### Known constraints (this environment)
| Constraint | Impact | Handling |
|-----------|--------|----------|
| Single GitHub account | Cannot enforce true 4-eyes (author == reviewer) | Risk-tier policy is the substitute |
| Branch protection needs Pro/public | No enforced review gate | CI gate + tier policy |
| Reviewer (Nemotron free) false positives | Wrong T3 flags waste human attention | Verify in Phase 1; use MiMo for T3 second review |
| Worker/planner subagents need `intercom` bridge | Pipeline stalls if bridge absent | Orchestrator runs Phases 2–3; reviewer subagent works |

---

## Agent → Model Mapping (current config)

| Agent | Model | Role in workflow |
|-------|-------|-----------------|
| `scout` | Hy3 (free) | Phase 0 discovery |
| `planner` | MiMo-V2.5 | Phase 1 verified issue |
| `worker` | MiMo-V2.5 | Phases 2–3 implementation + PR |
| `reviewer` | Nemotron 3 Ultra (free) | Phase 4 review + tier routing |
| `oracle` | MiMo-V2.5 | Escalation / direction check |
| `context-builder` | DeepSeek V4 Flash | Context synthesis |
| `researcher` | DeepSeek V4 Flash | External research |
| `delegate` | Hy3 (free) | Lightweight delegation |
