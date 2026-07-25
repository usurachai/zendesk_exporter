# Training Run Archive

Each subdirectory here records one training run on vast.ai — preserving everything
needed to reproduce or investigate the result later.

## Run Directory Structure

```
runs/2026-07-25_training_run_001/
├── run_summary.json      # Timestamp, instance, duration, exit code, data stats
├── config.yaml           # Snapshot of config/config.yaml at training time
├── score_report.txt      # Dataset quality score before training
├── training_output.log   # Full stdout from vast_train.sh on the remote instance
├── trainer_state.json    # Per-step loss + eval loss curve (from adapter checkpoint)
└── sample_outputs.txt    # Model responses to 5 probe prompts (optional)
```

## How Runs Are Created

- `vast_run.sh` automatically creates a run directory after each training session.
- The directory is named `YYYY-MM-DD_training_run_NNN` (sorted by date + auto-increment).
- If a run fails partway, partial artifacts are still preserved.

## How to Use a Run Record

**Reproduce a training run:**
```bash
cp runs/<DATE>_training_run_NNN/config.yaml config/config.yaml
cp runs/<DATE>_training_run_NNN/train.jsonl data/
cp runs/<DATE>_training_run_NNN/valid.jsonl data/
./vast_run.sh <INSTANCE_ID>
```

**Investigate loss curves:**
```bash
python3 -c "
import json
with open('runs/<DATE>_training_run_NNN/training_output.log') as f:
    print(f.read())  # search for 'loss' values
"
```