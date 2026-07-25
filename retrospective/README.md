# Retrospectives

This directory contains session retrospectives documenting what was accomplished, bugs found, and lessons learned.

## Naming Convention

```
YYYY-MM-DD_topic-slug.md
```

### Examples

| File | Date | Topic |
|------|------|-------|
| `2026-07-24_finetune-pipeline.md` | Jul 24, 2026 | Fine-tuning pipeline setup |
| `2026-07-25_dataset-cleanup.md` | Jul 25, 2026 | Dataset quality improvements |
| `2026-08-01_inference-testing.md` | Aug 1, 2026 | Inference testing session |
| `2026-08-01_inference-testing-v2.md` | Aug 1, 2026 | Same day, different session |

### Rules

1. **Date first** — enables chronological sorting: `ls retrospective/*.md | sort`
2. **Topic slug** — lowercase, hyphens not underscores, max 3-4 words
3. **Same day collisions** — append `-v2`, `-v3` suffix
4. **One topic per file** — don't combine unrelated work

## Template

Copy this template for new retrospectives:

```markdown
# Retrospective: [Title]

**Date:** YYYY-MM-DD
**Session:** [Brief description]
**Duration:** [Time spent]
**Agent:** [Who did the work]

---

## 🎯 Goal
[What we set out to do]

## 📊 Results
[Final outcomes table]

## 🔧 Deliverables
[Issues closed, PRs merged, commits]

## 🐛 Bugs Found & Fixed
[What broke and how we fixed it]

## 💡 Key Learnings
[What we learned for next time]

## ⏭️ Next Steps
[What to do next]
```
