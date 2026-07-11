"""Dataset Builder — converts raw Zendesk tickets into Unsloth-format conversation datasets.

Functional Requirements:
  FR-101: Identify customer using requester_id
  FR-102: Identify agent using author_id
  FR-103: Merge consecutive messages
  FR-104: Remove private notes
  FR-105: Remove empty messages
  FR-106: Preserve conversation order
  FR-107: Generate conversation statistics

  FR-201: Split dataset into train/valid
  FR-202: Random shuffle
  FR-203: Generate JSONL
  FR-204: Support configurable train ratio
  FR-205: Preserve message role
"""

import json
import random
from pathlib import Path
from typing import Any

from src.common.config import get_dataset_config
from src.common.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------
# Conversation Builder — Module 2  (FR-101 through FR-107)
# ---------------------------------------------------------------


def _is_public(comment: dict[str, Any]) -> bool:
    """Return True if the comment is public."""
    return comment.get("public", True)


def _is_non_empty(comment: dict[str, Any]) -> bool:
    """Return True if comment body is non-empty after stripping — FR-105."""
    return bool(comment.get("body", "").strip())


def build_conversation(ticket: dict[str, Any]) -> dict[str, Any] | None:
    """Convert a single raw ticket JSON into a conversation object.

    Returns None if the ticket has no usable public comments.
    """
    ticket_id = ticket.get("ticket_id") or ticket.get("id")
    requester_id = ticket.get("metadata", {}).get("requester_id")

    if requester_id is None:
        logger.warning("Ticket %s: missing requester_id, skipping", ticket_id)
        return None

    comments = ticket.get("comments", [])

    # FR-106: comments already sorted by created_at in exporter
    # FR-104: Remove private notes
    # FR-105: Remove empty messages
    filtered = [
        c for c in comments if _is_public(c) and _is_non_empty(c)
    ]

    if not filtered:
        logger.debug("Ticket %s: no usable public comments", ticket_id)
        return None

    # FR-103: Merge consecutive messages from the same author
    merged: list[dict[str, Any]] = []
    for comment in filtered:
        author_id = comment.get("author_id")
        body = comment["body"].strip()

        # FR-101: Identify customer using requester_id
        # FR-102: Identify agent using author_id (!= requester_id)
        role = "customer" if author_id == requester_id else "agent"

        if merged and merged[-1]["role"] == role:
            # Merge consecutive same-role messages
            merged[-1]["content"] += "\n" + body
            merged[-1]["comment_ids"].append(comment["id"])
        else:
            merged.append({
                "role": role,
                "content": body,
                "comment_ids": [comment["id"]],
            })

    if not merged:
        return None

    return {
        "ticket_id": ticket_id,
        "conversation": merged,
    }


# FR-107: Generate conversation statistics
def compute_stats(conversations: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute aggregate statistics across all conversations."""
    total = len(conversations)
    if total == 0:
        return {"total_conversations": 0}

    total_turns = sum(len(c["conversation"]) for c in conversations)
    customer_msgs = sum(
        sum(1 for m in c["conversation"] if m["role"] == "customer")
        for c in conversations
    )
    agent_msgs = total_turns - customer_msgs
    lengths = [len(c["conversation"]) for c in conversations]

    return {
        "total_conversations": total,
        "total_turns": total_turns,
        "customer_messages": customer_msgs,
        "agent_messages": agent_msgs,
        "avg_turns_per_conversation": round(total_turns / total, 1),
        "min_turns": min(lengths),
        "max_turns": max(lengths),
    }


# ---------------------------------------------------------------
# Dataset Generator — Module 3  (FR-201 through FR-205)
# ---------------------------------------------------------------


def _to_unsloth_format(
    conversation: dict[str, Any],
    system_prompt: str,
) -> dict[str, Any]:
    """Convert internal conversation object to Unsloth chat format — FR-205."""
    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt}
    ]

    for turn in conversation["conversation"]:
        role = "user" if turn["role"] == "customer" else "assistant"
        messages.append({"role": role, "content": turn["content"]})

    return {"messages": messages}


def generate_dataset(
    raw_dir: str,
    output_dir: str,
    train_ratio: float = 0.9,
    shuffle_seed: int = 42,
    system_prompt: str = "",
) -> dict[str, Any]:
    """Build conversations from raw tickets and generate train/valid JSONL files.

    Args:
        raw_dir: Directory containing ticket_*.json files.
        output_dir: Directory to write train.jsonl and valid.jsonl.
        train_ratio: Proportion for training split (0.0–1.0) — FR-204.
        shuffle_seed: Seed for reproducible shuffle — FR-202.
        system_prompt: System prompt to inject.

    Returns:
        Summary dict with counts and output paths.
    """
    raw_path = Path(raw_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Load all raw tickets
    ticket_files = sorted(raw_path.glob("ticket_*.json"))
    logger.info("Processing %d raw ticket files from %s", len(ticket_files), raw_dir)

    conversations: list[dict[str, Any]] = []
    skipped = 0
    for tf in ticket_files:
        try:
            ticket = json.loads(tf.read_text())
        except json.JSONDecodeError:
            logger.warning("Skipping corrupt file: %s", tf.name)
            skipped += 1
            continue

        conv = build_conversation(ticket)
        if conv:
            conversations.append(conv)
        else:
            skipped += 1

    logger.info("Built %d conversations (%d skipped)", len(conversations), skipped)

    if not conversations:
        logger.error("No conversations built. Check your raw data.")
        return {"error": "no_conversations", "train_count": 0, "valid_count": 0}

    # FR-202: Random shuffle
    rng = random.Random(shuffle_seed)
    rng.shuffle(conversations)

    # FR-201: Split dataset
    # FR-204: Configurable train ratio
    split_idx = max(1, int(len(conversations) * train_ratio))
    train_convs = conversations[:split_idx]
    valid_convs = conversations[split_idx:]

    # FR-203: Generate JSONL
    train_path = output_path / "train.jsonl"
    valid_path = output_path / "valid.jsonl"

    _write_jsonl(train_convs, train_path, system_prompt)
    _write_jsonl(valid_convs, valid_path, system_prompt)

    # FR-107: Stats
    train_stats = compute_stats(train_convs)
    valid_stats = compute_stats(valid_convs)

    summary = {
        "train_count": len(train_convs),
        "valid_count": len(valid_convs),
        "train_path": str(train_path),
        "valid_path": str(valid_path),
        "train_stats": train_stats,
        "valid_stats": valid_stats,
    }

    logger.info("Dataset generated: %d train / %d valid", len(train_convs), len(valid_convs))
    return summary


def _write_jsonl(
    conversations: list[dict[str, Any]],
    output_path: Path,
    system_prompt: str,
) -> None:
    """Write conversations to a JSONL file in Unsloth format."""
    with open(output_path, "w", encoding="utf-8") as fh:
        for conv in conversations:
            formatted = _to_unsloth_format(conv, system_prompt)
            fh.write(json.dumps(formatted, ensure_ascii=False) + "\n")
    logger.info("Wrote %d records to %s", len(conversations), output_path)
