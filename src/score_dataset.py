"""Dataset quality scoring — evaluates a prepared dataset for fine-tuning fitness.

Scores 0-100 across five dimensions. Run with ``run_score.py``.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from collections.abc import Sequence

logger = logging.getLogger("src.score_dataset")


# ---------------------------------------------------------------------------
#  Scored dimensions  (the rubric)
# ---------------------------------------------------------------------------

# Dimension weightings (sum = 100)
WEIGHTS = {
    "pipeline_integrity": 15,
    "content_safety": 20,
    "cleaning_dedup": 25,
    "dataset_fitness": 25,
    "config_engineering": 15,
}

MAX_SCORE = sum(WEIGHTS.values())  # 100


class DatasetScore:
    """Holds all raw metrics and computed scores for one dataset evaluation."""

    def __init__(self, train: list[dict], valid: list[dict], config: dict):
        self.train = train
        self.valid = valid
        self.config = config

        # Raw data stats — populated by _measure()
        self.total_raw: int = 0
        self.conv_count: int = 0
        self.skip_count: int = 0
        self.turn_counts: list[int] = []
        self.user_count: int = 0
        self.assistant_count: int = 0
        self.system_prompt_count: int = 1
        self.sample_message_lens: list[int] = []
        self.empty_message_count: int = 0
        self.pii_leaks: list[tuple[str, str, str]] = []  # (split, role, content_snippet)
        self.url_leaks: list[tuple[str, str]] = []  # (split, role)
        self.canned_dropped: int = 0
        self.canned_stripped: int = 0
        self.sentence_dropped: int = 0
        self.duplicate_dropped: int = 0
        self.broken_dropped: int = 0

    # ---- measurement -----------------------------------------------------

    def _measure(self) -> None:
        """Collect all raw metrics from train + valid data."""
        t = self.train
        v = self.valid

        self.conv_count = len(t) + len(v)

        _phone_re = re.compile(r"0\d{1,2}[-\s]?\d{3}[-\s]?\d{4}")
        _email_re = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")
        _url_re = re.compile(r"https?://\S+")
        _safe_patterns = self.config.get("dataset", {}).get("pii_safe_patterns", [])

        for split_name, data in [("train", t), ("valid", v)]:
            for c in data:
                # Skip system prompt at index 0
                messages = c.get("messages", [])
                if len(messages) < 2:
                    continue
                turn_len = len(messages) - 1  # exclude system
                self.turn_counts.append(turn_len)

                for m in messages[1:]:
                    role = m["role"]
                    if role == "user":
                        self.user_count += 1
                    elif role == "assistant":
                        self.assistant_count += 1

                    content = m.get("content", "")
                    self.sample_message_lens.append(len(content))

                    if not content.strip():
                        self.empty_message_count += 1

                    # PII scan
                    for p in _phone_re.findall(content):
                        self.pii_leaks.append((split_name, role, p))
                    for e in _email_re.findall(content):
                        if e not in _safe_patterns:
                            self.pii_leaks.append((split_name, role, e))

                    # URL scan
                    if _url_re.search(content):
                        self.url_leaks.append((split_name, role))

    # ---- dimension scores ------------------------------------------------

    def _score_pipeline_integrity(self) -> float:
        """15 pts — conversion rate + file health."""
        score = 0.0
        conv_rate = self.conv_count / (self.conv_count + self.skip_count) if (self.conv_count + self.skip_count) > 0 else 0

        # 10 pts for conversion rate
        if conv_rate >= 0.98:
            score += 10
        elif conv_rate >= 0.95:
            score += 7
        elif conv_rate >= 0.90:
            score += 4

        # 5 pts if no JSON/IO errors (proxied: skip_count tracked)
        if self.skip_count == 0:
            score += 5
        elif self.skip_count <= 5:
            score += 3

        return score

    def _score_content_safety(self) -> float:
        """20 pts — PII, URL leaks, empty messages."""
        score = 0.0

        # 10 pts for PII
        pii_found = len(self.pii_leaks)
        if pii_found == 0:
            score += 10
        elif pii_found <= 3:
            score += 7
        elif pii_found <= 10:
            score += 4

        # 6 pts for URL leaks
        # If clean_urls is on, raw URLs are a problem; if off, not a safety issue
        clean_urls = self.config.get("dataset", {}).get("clean_urls", False)
        if not clean_urls:
            score += 6  # config says keep URLs, so not a leak
        else:
            url_leak_count = len(self.url_leaks)
            if url_leak_count == 0:
                score += 6
            elif url_leak_count <= 5:
                score += 4
            elif url_leak_count <= 20:
                score += 2

        # 4 pts for empty messages
        empty_ratio = self.empty_message_count / max(len(self.turn_counts), 1)
        if empty_ratio == 0:
            score += 4
        elif empty_ratio <= 0.001:
            score += 3
        elif empty_ratio <= 0.01:
            score += 1

        return score

    def _score_cleaning_dedup(self) -> float:
        """25 pts — dedup, filler, canned, artifacts."""
        score = 0.0

        train_valid_total = len(self.turn_counts)
        if train_valid_total == 0:
            return 0.0

        # 8 pts — canned dedup
        if self.canned_dropped > 0 or self.canned_stripped > 0:
            stripped_ratio = self.canned_stripped / max(train_valid_total, 1)
            if stripped_ratio >= 0.3 and stripped_ratio <= 2.0:
                score += 8  # meaningful but not excessive
            elif stripped_ratio > 0:
                score += 5
        else:
            score += 4  # canned dedup off?

        # 6 pts — sentence dedup
        if self.sentence_dropped > 0:
            dropped_ratio = self.sentence_dropped / max(train_valid_total, 1)
            if dropped_ratio >= 0.5 and dropped_ratio <= 3.0:
                score += 6
            elif dropped_ratio > 0:
                score += 4

        # 5 pts — exact dedup
        if self.duplicate_dropped >= 100:
            score += 4  # meaningful dedup
        elif self.duplicate_dropped > 0:
            score += 3

        # 6 pts — no artifacts
        # Check boundary noise, garbled text, empty messages
        has_garbling = self._check_garbling()
        if self.empty_message_count == 0 and not has_garbling:
            score += 6
        elif self.empty_message_count <= 3 and not has_garbling:
            score += 4
        else:
            score += 2

        return score

    def _check_garbling(self) -> bool:
        """Quick heuristic for garbled text artifacts.

        Patterns are specific to avoid false-flagging legitimate words:
        "scription" matched "subscription", "description", etc.
        """
        garbled_patterns = [
            r"(?<!\w)bscription",  # garbled "bscription", not "subscription"
            "ม่สะดวก",                 # garbled "ไม่สะดวก"
            "ต่าหาก",                  # garbled "ต่างหาก"
            "https://forms",
            "://forms.",
        ]
        for split in (self.train, self.valid):
            for c in split:
                for m in c.get("messages", []):
                    content = m.get("content", "")
                    for pat in garbled_patterns:
                        if re.search(pat, content):
                            return True
        return False

    def _score_dataset_fitness(self) -> float:
        """25 pts — role balance, depth, split quality, content length."""
        score = 0.0
        total = len(self.turn_counts)
        if total == 0:
            return 0.0

        # 8 pts — role balance
        total_msgs = self.user_count + self.assistant_count
        if total_msgs > 0:
            user_ratio = self.user_count / total_msgs
            if 0.45 <= user_ratio <= 0.55:
                score += 8  # near-perfect balance
            elif 0.35 <= user_ratio <= 0.65:
                score += 5
            else:
                score += 2

        # 8 pts — turn depth
        min_t = min(self.turn_counts)
        avg_t = sum(self.turn_counts) / total
        one_turn_ratio = sum(1 for t in self.turn_counts if t == 1) / total

        if avg_t >= 5 and one_turn_ratio <= 0.01 and min_t >= 2:
            score += 8
        elif avg_t >= 4 and one_turn_ratio <= 0.05:
            score += 5
        elif avg_t >= 3:
            score += 3

        # 5 pts — train/valid split
        valid_ratio = len(self.valid) / (len(self.train) + len(self.valid))
        if 0.08 <= valid_ratio <= 0.15:
            score += 5
        elif 0.05 <= valid_ratio <= 0.20:
            score += 3

        # 4 pts — content length
        avg_len = sum(self.sample_message_lens) / max(len(self.sample_message_lens), 1)
        if avg_len >= 80:
            score += 4
        elif avg_len >= 50:
            score += 3
        elif avg_len >= 30:
            score += 2

        return score

    def _score_config_engineering(self) -> float:
        """15 pts — config-driven, reproducible, logging."""
        score = 0.0

        # 5 pts — config-driven
        ds_cfg = self.config.get("dataset", {})
        config_keys = [
            "train_ratio", "shuffle_seed", "agent_names",
            "clean_attachments", "clean_urls",
            "redact_pii", "pii_safe_patterns",
            "dedupe_canned", "dedupe_exact", "dedupe_sentences",
            "clean_fillers", "drop_filler_only", "min_message_length",
            "filter_sentences",
        ]
        found = sum(1 for k in config_keys if k in ds_cfg)
        ratio = found / len(config_keys)
        score += 5 * ratio

        # 5 pts — reproducibility (seed, deterministic)
        if ds_cfg.get("shuffle_seed") is not None:
            score += 5

        # 5 pts — logging / stats
        # Only award when logging handlers are actually wired up
        if logging.getLogger().handlers or logger.handlers:
            score += 5

        return score

    # ---- public API ------------------------------------------------------

    def compute(self, pipeline_stats: dict | None = None) -> dict:
        """Run all measurements and return full score breakdown."""
        # Seed with pipeline stats if provided
        if pipeline_stats:
            # extract from nested structure (score_stats.json) or flat dict (inline)
            ps = pipeline_stats
            # support both flat keys and nested under "train_stats"/"valid_stats"
            self.total_raw = ps.get("total_raw", self.total_raw)
            self.skip_count = (
                ps.get("skip_count", 0)
                or (self.total_raw - self.conv_count if self.total_raw else 0)
            )
            self.duplicate_dropped = ps.get("duplicate_dropped", 0) or ps.get("duplicate_occurrences_dropped", 0)
            self.broken_dropped = ps.get("broken_dropped", 0) or ps.get("broken_conversations_dropped", 0)
            self.sentence_dropped = ps.get("sentence_dropped", 0) or ps.get("sentence_occurrences_dropped", 0)
            self.canned_dropped = ps.get("canned_dropped", 0) or ps.get("canned_dominated_dropped", 0)
            self.canned_stripped = ps.get("canned_stripped", 0) or ps.get("canned_suffix_stripped", 0)

        # If we still have zero counts but total_raw is set, infer
        if self.total_raw > 0 and self.skip_count == 0:
            self.skip_count = max(0, self.total_raw - self.conv_count)

        self._measure()

        scores = {
            "pipeline_integrity": round(self._score_pipeline_integrity(), 1),
            "content_safety": round(self._score_content_safety(), 1),
            "cleaning_dedup": round(self._score_cleaning_dedup(), 1),
            "dataset_fitness": round(self._score_dataset_fitness(), 1),
            "config_engineering": round(self._score_config_engineering(), 1),
        }
        total = round(sum(scores.values()), 1)

        return {
            "total": total,
            "max_score": MAX_SCORE,
            "dimensions": scores,
            "weights": WEIGHTS,
            "metrics": {
                "conversation_count": self.conv_count,
                "skip_count": self.skip_count,
                "train_count": len(self.train),
                "valid_count": len(self.valid),
                "turn_stats": {
                    "min": min(self.turn_counts) if self.turn_counts else 0,
                    "max": max(self.turn_counts) if self.turn_counts else 0,
                    "avg": round(sum(self.turn_counts) / max(len(self.turn_counts), 1), 1),
                },
                "role_balance": {
                    "user": self.user_count,
                    "assistant": self.assistant_count,
                    "user_ratio": round(self.user_count / max(self.user_count + self.assistant_count, 1), 3),
                },
                "pii_leaks": self.pii_leaks,
                "url_leaks_count": len(self.url_leaks),
                "empty_messages": self.empty_message_count,
                "avg_content_length_chars": round(
                    sum(self.sample_message_lens) / max(len(self.sample_message_lens), 1), 1
                ),
                "dedup": {
                    "exact_dropped": self.duplicate_dropped,
                    "broken_dropped": self.broken_dropped,
                    "sentence_dropped": self.sentence_dropped,
                    "canned_stripped": self.canned_stripped,
                    "canned_dropped": self.canned_dropped,
                },
            },
        }


def score_dataset(
    train_path: str = "data/train.jsonl",
    valid_path: str = "data/valid.jsonl",
    config_path: str = "config/config.yaml",
    pipeline_stats: dict | None = None,
) -> dict:
    """Load a dataset + config and return the score breakdown.

    Parameters
    ----------
    train_path, valid_path : str
        Paths to the generated JSONL files.
    config_path : str
        Path to the config YAML (used for scoring config_engineering).
    pipeline_stats : dict or None
        Stats from the pipeline run (dropped counts etc).

    Returns
    -------
    dict with keys *total*, *max_score*, *dimensions*, *weights*, *metrics*.
    """
    import yaml

    with open(config_path) as f:
        config = yaml.safe_load(f) or {}

    train: list[dict] = []
    if os.path.exists(train_path):
        with open(train_path) as f:
            train = [json.loads(l) for l in f if l.strip()]
    else:
        logger.warning("train.jsonl not found at %s", train_path)

    valid: list[dict] = []
    if os.path.exists(valid_path):
        with open(valid_path) as f:
            valid = [json.loads(l) for l in f if l.strip()]
    else:
        logger.warning("valid.jsonl not found at %s", valid_path)

    scorer = DatasetScore(train, valid, config)
    result = scorer.compute(pipeline_stats=pipeline_stats)

    return result


def format_report(result: dict, verbose: bool = False) -> str:
    """Pretty-print a score result dict as a human-readable report."""
    lines = []
    lines.append("=" * 62)
    lines.append(f"  DATASET QUALITY SCORE:  {result['total']:.0f} / {result['max_score']}")
    lines.append("=" * 62)
    lines.append("")

    for dim, score in result["dimensions"].items():
        label = dim.replace("_", " ").title()
        weight = result["weights"].get(dim, 0)
        bar_len = int(score / result["max_score"] * 40)
        bar = "█" * bar_len + "░" * (40 - bar_len)
        lines.append(f"  {label:20s}  {score:5.1f}/{weight:<3d}  {bar}")

    lines.append("")
    lines.append("-" * 62)
    lines.append("  KEY METRICS")
    lines.append("-" * 62)
    m = result.get("metrics", {})

    lines.append(f"  Conversations:     {m.get('conversation_count', '?'):>6d}  ({m.get('train_count', '?')} train + {m.get('valid_count', '?')} valid)")
    if m.get("skip_count"):
        lines.append(f"  Skipped:           {m['skip_count']:>6d}")

    turn = m.get("turn_stats", {})
    lines.append(f"  Turns/conversation:  min={turn.get('min', '?')} avg={turn.get('avg', '?')} max={turn.get('max', '?')}")

    rb = m.get("role_balance", {})
    lines.append(f"  Role balance:        {rb.get('user', '?')} user / {rb.get('assistant', '?')} assistant  ({rb.get('user_ratio', '?')})")

    lines.append(f"  Avg message length:  {m.get('avg_content_length_chars', '?')} chars")
    lines.append(f"  Empty messages:      {m.get('empty_messages', '?')}")

    pii = m.get("pii_leaks", [])
    lines.append(f"  PII leaks:           {len(pii)}")
    if pii and verbose:
        for s, r, v in pii[:10]:
            lines.append(f"    [{s}/{r}] {v}")

    lines.append(f"  URL leaks:           {m.get('url_leaks_count', '?')}")

    dd = m.get("dedup", {})
    if dd:
        lines.append(f"  Duplicates dropped:  {dd.get('exact_dropped', '?')}")
        lines.append(f"  Broken dropped:      {dd.get('broken_dropped', '?')}")
        lines.append(f"  Sentence dropped:    {dd.get('sentence_dropped', '?')}")
        lines.append(f"  Canned stripped:     {dd.get('canned_stripped', '?')}")
        lines.append(f"  Canned dropped:      {dd.get('canned_dropped', '?')}")

    lines.append("")
    lines.append(f"  {'★ PASS' if result['total'] >= 70 else '☆ NEEDS WORK':>30s}  (threshold: 70/100)")
    lines.append("=" * 62)

    return "\n".join(lines)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Score dataset quality")
    parser.add_argument("--train", default="data/train.jsonl")
    parser.add_argument("--valid", default="data/valid.jsonl")
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    result = score_dataset(train_path=args.train, valid_path=args.valid, config_path=args.config)
    print()
    print(format_report(result, verbose=args.verbose))