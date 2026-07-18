# Progress: fix/canned-boundary-threshold

## Step 1: Branch created
- Branch: `fix/canned-boundary-threshold`
- Status: ✅ done

## Step 2: Read `_remove_canned_phrase()`
- Found at `src/dataset.py:974`
- Current boundary logic: `at_start = idx <= 10`, `at_end = (body_len - (idx + sig_len)) < 10`
- Status: ✅ done

## Step 3: Apply fix
- Changed `at_start = idx <= 10` → `at_start = idx <= 2`
- `at_end` threshold unchanged at `< 10`
- Status: ✅ done

## Step 4: Run tests
- All 55 tests passed
- Status: ✅ done

## Step 5: Commit
- Commit: `94a3aa8` — `fix: tighten canned phrase start boundary from <=10 to <=2 - closes #1`
- Status: ✅ done

## Step 6: Push
- Pushed to `origin fix/canned-boundary-threshold`
- Status: ✅ done

## Step 7: Open PR
- PR: https://github.com/usurachai/zendesk_exporter/pull/11
- Title: "fix: tighten canned phrase boundary threshold"
- Status: ✅ done