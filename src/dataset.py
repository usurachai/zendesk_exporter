"""Dataset Builder — converts raw Zendesk tickets into Unsloth-format conversation datasets.

Supports two Zendesk data formats:
  - Native: author_id distinguishes customer (requester_id) vs agent
  - Sunshine Conversations: author_id=-1, names embedded in body as
    "(HH:MM:SS) Name: message" — customer name extracted from private
    "Conversation with <Name>" comment.

Functional Requirements:
  FR-101: Identify customer using requester_id (native) or name matching (Sunshine)
  FR-102: Identify agent using author_id (native) or non-customer name (Sunshine)
  FR-103: Merge consecutive messages from the same speaker
  FR-104: Remove private notes (keep only for name extraction)
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
import re
from pathlib import Path
from typing import Any

from src.common.config import get_dataset_config
from src.common.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------
# Sunshine Conversations helpers
# ---------------------------------------------------------------

# Matches "(HH:MM:SS) Name: " or "(HH:MM:SS) Name uploaded: " at start of body
_SUNSHINE_AUTHOR_RE = re.compile(
    r"^\((\d{2}:\d{2}:\d{2})\)\s+(.+?)(?:\suploaded)?:\s+"
)

# Splits on "(HH:MM:SS) " boundaries — each segment is one person's message(s)
_SUNSHINE_SPLIT_RE = re.compile(r"(?=\(\d{2}:\d{2}:\d{2}\)\s+)")

# Matches private comment "Conversation with <Name>"
_CONVERSATION_WITH_RE = re.compile(r"^Conversation\s+with\s+(.+)", re.IGNORECASE)


def _extract_customer_name(comments: list[dict[str, Any]]) -> str | None:
    """Extract customer name from Sunshine Conversations private comment.

    Scans private comments for "Conversation with <Name>".
    """
    for c in comments:
        if not c.get("public", True):
            m = _CONVERSATION_WITH_RE.match(c.get("body", "").strip())
            if m:
                return m.group(1).strip()
    return None


def _split_sunshine_messages(
    body: str,
    customer_name: str,
    agent_names: set[str],
) -> list[tuple[str, str]]:
    """Split a Sunshine Conversations comment body into individual messages.

    A single Zendesk comment can contain multiple messages from different
    speakers. This splits at each "(HH:MM:SS) Name:" boundary and classifies
    each sub-message as customer or agent.

    Classification priority:
      1. Name matches known agent list → agent
      2. Name matches customer name → customer
      3. Otherwise → agent (safe default)

    Returns list of (role, cleaned_body) tuples.
    """
    # Split on timestamp boundaries, discard leading empty string
    segments = [s.strip() for s in _SUNSHINE_SPLIT_RE.split(body.strip()) if s.strip()]

    results: list[tuple[str, str]] = []
    for seg in segments:
        m = _SUNSHINE_AUTHOR_RE.match(seg)
        if not m:
            continue

        author = m.group(2).strip()
        # Remove the "(HH:MM:SS) Name: " prefix
        cleaned = _SUNSHINE_AUTHOR_RE.sub("", seg, count=1).strip()

        if not cleaned:
            continue  # skip attachment-only segments with no text

        # Classification: known agent > customer match > default agent
        if author in agent_names:
            role = "agent"
        elif author.lower() == customer_name.lower():
            role = "customer"
        else:
            logger.debug("Unknown speaker '%s' — classifying as agent", author)
            role = "agent"

        results.append((role, cleaned))

    return results


def _is_sunshine_format(comments: list[dict[str, Any]]) -> bool:
    """Detect if this ticket uses the Sunshine Conversations format.

    True if any public comment has author_id=-1 and body matches the pattern.
    """
    for c in comments:
        if c.get("public", True) and c.get("author_id") == -1:
            if _SUNSHINE_AUTHOR_RE.match(c.get("body", "").strip()):
                return True
    return False


# ---------------------------------------------------------------
# Conversation Builder — Module 2  (FR-101 through FR-107)
# ---------------------------------------------------------------


def _is_public(comment: dict[str, Any]) -> bool:
    """Return True if the comment is public."""
    return comment.get("public", True)


def _is_non_empty(comment: dict[str, Any]) -> bool:
    """Return True if comment body is non-empty after stripping — FR-105."""
    return bool(comment.get("body", "").strip())


def _classify_sunshine(
    body: str,
    customer_name: str,
) -> tuple[str, str]:
    """Classify a Sunshine Conversations message as customer or agent.

    Returns (role, cleaned_body).
    """
    author = _parse_sunshine_author(body)
    cleaned = _strip_sunshine_prefix(body)

    if author and author.lower() == customer_name.lower():
        return "customer", cleaned
    else:
        return "agent", cleaned


def build_conversation(
    ticket: dict[str, Any],
    agent_names: set[str] | None = None,
) -> dict[str, Any] | None:
    """Convert a single raw ticket JSON into a conversation object.

    Handles both native Zendesk format and Sunshine Conversations format.

    Returns None if the ticket has no usable public comments.
    """
    ticket_id = ticket.get("ticket_id") or ticket.get("id")
    requester_id = ticket.get("metadata", {}).get("requester_id")
    comments = ticket.get("comments", [])

    if not comments:
        return None

    # Detect format
    sunshine = _is_sunshine_format(comments)
    customer_name: str | None = None

    if sunshine:
        customer_name = _extract_customer_name(comments)
        if not customer_name:
            logger.warning(
                "Ticket %s: Sunshine format detected but no 'Conversation with' "
                "private comment found. Falling back to requester_id.",
                ticket_id,
            )

    # Filter public, non-empty — FR-104, FR-105
    filtered = [
        c for c in comments if _is_public(c) and _is_non_empty(c)
    ]

    if not filtered:
        logger.debug("Ticket %s: no usable public comments", ticket_id)
        return None

    # Build turns — FR-103 (merge consecutive same-role), FR-106 (order)
    merged: list[dict[str, Any]] = []
    for comment in filtered:
        body = comment["body"].strip()
        author_id = comment.get("author_id")

        if sunshine and customer_name:
            # Split multi-message Sunshine comment into individual messages
            sub_messages = _split_sunshine_messages(body, customer_name, agent_names or set())
        else:
            # Native format: FR-101, FR-102
            role = "customer" if author_id == requester_id else "agent"
            sub_messages = [(role, body)]

        for role, clean_body in sub_messages:
            if not clean_body:
                continue  # FR-105: skip after strip

            if merged and merged[-1]["role"] == role:
                merged[-1]["content"] += "\n" + clean_body
                merged[-1]["comment_ids"].append(comment["id"])
            else:
                merged.append({
                    "role": role,
                    "content": clean_body,
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
    agent_names: list[str] | None = None,
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

        conv = build_conversation(ticket, agent_names=set(agent_names or []))
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
