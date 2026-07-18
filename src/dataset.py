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
# Message cleanup
# ---------------------------------------------------------------

# Matches attachment metadata block: "filename\nURL: ...\nType: ...\nSize: ..."
_ATTACHMENT_META_RE = re.compile(
    r"[\w.-]+\.(?:jpe?g|png|gif|mp4|pdf|webp|bmp)\n"
    r"URL:\s*https?://[^\n]+\n"
    r"Type:\s*[^\n]+\n"
    r"Size:\s*\d+"
)

_URL_RE = re.compile(r"https?://\S+")

# Canned message detection — dynamic via frequency analysis (no hardcoded patterns)
_CANNED_MIN_LEN = 25   # minimum substring length for primary detection
_CANNED_MIN_FREQ = 5   # minimum occurrences for primary detection
# Second-pass: short phrases that appear extremely often (>50x) are likely templates
_SHORT_CANNED_MIN_LEN = 15
_SHORT_CANNED_MIN_FREQ = 30

# Thai filler/particle words
_TRAILING_FILLERS = [
    "ครับ", "ครับผม", "คับ", "คะ", "ค่ะ", "ค้า",
    "นะครับ", "นะคะ", "นะฮะ", "นะ", "นะจ๊ะ",
    "ฮะ", "ฮ่ะ", "จ้า", "จร้า", "เด้อ", "เลย",
    "อ่ะ", "อะ", "น่ะ", "คะน้า", "ค่า", "คร้าบ",
]

# Build trailing-filler regex from safe escaped words
_ESCAPED_FILLERS = "|".join(re.escape(w) for w in sorted(_TRAILING_FILLERS, key=len, reverse=True))
_TRAILING_FILLERS_RE = re.compile(
    rf"\s*(?:{_ESCAPED_FILLERS})\s*$",
    re.IGNORECASE,
)


def _is_filler_only(body: str) -> bool:
    """Return True if the message is nothing but filler words/repetitions."""
    body = body.strip().lower()
    # Remove all known filler words and whitespace
    remaining = body
    for w in sorted(_TRAILING_FILLERS, key=len, reverse=True):
        remaining = remaining.replace(w.lower(), " ")
    # Also remove repetitions like ๆๆ
    remaining = remaining.replace("ๆ", " ")
    remaining = remaining.strip()
    return remaining == ""


def _clean_fillers(body: str) -> str | None:
    """Strip trailing filler particles from a message.

    Returns None if the message becomes empty after cleaning.
    """
    cleaned = _TRAILING_FILLERS_RE.sub("", body).strip()
    if not cleaned:
        return None
    return cleaned

# PII patterns for redaction
_PHONE_RE = re.compile(r"0\d{1,2}[-\s]?\d{3}[-\s]?\d{4}")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")


def _discover_canned_signatures(
    conversations: list[dict[str, Any]],
    min_len: int = _CANNED_MIN_LEN,
    min_freq: int = _CANNED_MIN_FREQ,
) -> set[str]:
    """Dynamically discover canned/template signatures from the dataset.

    Finds long substrings that appear in many different messages across
    the dataset — these are likely canned responses (apology templates,
    closing messages, etc.). No hardcoded patterns needed.
    """
    from collections import Counter

    # Collect all non-trivial messages, strip URLs to prevent URL
    # fragments from being detected as canned signatures
    messages: list[str] = []
    for conv in conversations:
        for turn in conv["conversation"]:
            body = " ".join(turn["content"].split())
            body = _URL_RE.sub("[url]", body)
            if len(body) >= min_len:
                messages.append(body)

    if len(messages) < min_freq:
        return set()

    # Sample substrings for performance (every Nth position)
    sub_freq: Counter = Counter()
    for body in messages:
        step = max(1, len(body) // 30)
        for i in range(0, max(1, len(body) - min_len), step):
            sub = body[i:i + min_len]
            if len(sub) >= min_len:
                sub_freq[sub] += 1

    signatures = {s for s, c in sub_freq.items() if c >= min_freq}

    # Second pass: detect short but extremely frequent phrases
    # (e.g., "(ยกเว้นวันหยุด)" at 14 chars appearing 300+ times)
    if min_len > _SHORT_CANNED_MIN_LEN:
        short_freq: Counter = Counter()
        for body in messages:
            if len(body) < _SHORT_CANNED_MIN_LEN:
                continue
            step = max(1, len(body) // 30)
            for i in range(0, max(1, len(body) - _SHORT_CANNED_MIN_LEN), step):
                sub = body[i:i + _SHORT_CANNED_MIN_LEN]
                if len(sub) >= _SHORT_CANNED_MIN_LEN:
                    short_freq[sub] += 1

        short_sigs = {s for s, c in short_freq.items() if c >= _SHORT_CANNED_MIN_FREQ}
        if short_sigs:
            logger.info(
                "Short-phrase detection: %d signatures (min_len=%d, min_freq=%d)",
                len(short_sigs), _SHORT_CANNED_MIN_LEN, _SHORT_CANNED_MIN_FREQ,
            )
        signatures |= short_sigs

    if signatures:
        logger.info(
            "Dynamic canned detection: %d signatures (min_len=%d, min_freq=%d)",
            len(signatures), min_len, min_freq,
        )
    return signatures


def _contains_canned(body: str, signatures: set[str]) -> bool:
    """Check if a message contains any canned signature substring."""
    normalized = " ".join(body.split())
    for sig in signatures:
        if sig in normalized:
            return True
    return False


def _redact_pii(body: str, safe_patterns: list[str] | None = None) -> str:
    """Redact phone numbers and email addresses from message body.

    Safe patterns (e.g. company support email) are preserved.
    """
    safe = set(safe_patterns or [])

    def _replace_email(m: re.Match) -> str:
        if m.group(0) in safe:
            return m.group(0)
        return "[email]"

    body = _EMAIL_RE.sub(_replace_email, body)
    body = _PHONE_RE.sub("[phone]", body)

    return body


def _clean_message(
    body: str,
    clean_attachments: bool = True,
    clean_urls: bool = True,
    redact_pii: bool = True,
    clean_fillers: bool = True,
    pii_safe_patterns: list[str] | None = None,
) -> str | None:
    """Clean a message body for training quality.

    Returns the cleaned body, or None if the message should be dropped.
    """
    if clean_attachments:
        # Strip attachment metadata blocks
        body = _ATTACHMENT_META_RE.sub("[image]", body).strip()

        # Collapse multiple [image] placeholders
        body = re.sub(r"(\[image\]\s*){2,}", "[images]", body)

    if clean_urls:
        # Replace standalone URLs with [link]
        body = _URL_RE.sub("[link]", body)

    # Remove repeated [image] [link] noise
    body = re.sub(r"^\[image\]\s*", "", body)
    body = re.sub(r"^\[link\]\s*", "", body)

    if redact_pii:
        body = _redact_pii(body, safe_patterns=pii_safe_patterns)

    if clean_fillers:
        body = _clean_fillers(body)
        if body is None:
            return None  # dropped — became empty after filler strip

    return body.strip()


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
    clean_attachments: bool = True,
    clean_urls: bool = True,
    redact_pii: bool = True,
    clean_fillers: bool = True,
    drop_filler_only: bool = True,
    pii_safe_patterns: list[str] | None = None,
    min_length: int = 3,
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
            # Apply quality cleanup
            clean_body = _clean_message(
                clean_body,
                clean_attachments=clean_attachments,
                clean_urls=clean_urls,
                redact_pii=redact_pii,
                clean_fillers=clean_fillers,
                pii_safe_patterns=pii_safe_patterns,
            )

            if not clean_body:
                continue  # dropped by cleanup

            if drop_filler_only and _is_filler_only(clean_body):
                continue  # noise: "ครับ", "ฮะ", "โอเคค่ะ" etc.

            if len(clean_body) < min_length:
                continue  # FR-105: too short

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


# ---------------------------------------------------------------
# Shared: build conversations from raw files (used by both
# generate_dataset and --analyze)
# ---------------------------------------------------------------


def _build_conversations(
    raw_dir: str,
    agent_names: set[str] | None = None,
    clean_attachments: bool = True,
    clean_urls: bool = True,
    redact_pii: bool = True,
    clean_fillers: bool = True,
    drop_filler_only: bool = True,
    pii_safe_patterns: list[str] | None = None,
    min_length: int = 3,
) -> list[dict[str, Any]]:
    """Load all raw ticket files and build conversation objects.

    Shared helper used by both generate_dataset and --analyze mode.
    Returns list of conversation dicts. Handles corrupt files gracefully.
    """
    raw_path = Path(raw_dir)
    ticket_files = sorted(raw_path.glob("ticket_*.json"))
    logger.info("Processing %d raw ticket files from %s", len(ticket_files), raw_dir)

    conversations: list[dict[str, Any]] = []
    skipped = 0
    for tf in ticket_files:
        try:
            ticket = json.loads(tf.read_text())
        except (json.JSONDecodeError, OSError):
            logger.warning("Skipping corrupt/unreadable file: %s", tf.name)
            skipped += 1
            continue

        conv = build_conversation(
            ticket,
            agent_names=agent_names or set(),
            clean_attachments=clean_attachments,
            clean_urls=clean_urls,
            redact_pii=redact_pii,
            clean_fillers=clean_fillers,
            drop_filler_only=drop_filler_only,
            pii_safe_patterns=pii_safe_patterns,
            min_length=min_length,
        )
        if conv:
            conversations.append(conv)
        else:
            skipped += 1

    logger.info("Built %d conversations (%d skipped)", len(conversations), skipped)
    return conversations


def generate_dataset(
    raw_dir: str,
    output_dir: str,
    train_ratio: float = 0.9,
    shuffle_seed: int = 42,
    system_prompt: str = "",
    agent_names: list[str] | None = None,
    clean_attachments: bool = True,
    clean_urls: bool = True,
    dedupe_canned: bool = True,
    redact_pii: bool = True,
    clean_fillers: bool = True,
    drop_filler_only: bool = True,
    pii_safe_patterns: list[str] | None = None,
    dedupe_exact: bool = True,
    max_duplicate_count: int = 3,
    dedupe_sentences: bool = True,
    filter_sentences: list[str] | None = None,
    min_message_length: int = 3,
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

    # Load all raw tickets → conversation objects
    conversations = _build_conversations(
        raw_dir=raw_dir,
        agent_names=set(agent_names or []),
        clean_attachments=clean_attachments,
        clean_urls=clean_urls,
        redact_pii=redact_pii,
        clean_fillers=clean_fillers,
        drop_filler_only=drop_filler_only,
        pii_safe_patterns=pii_safe_patterns,
        min_length=min_message_length,
    )

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

    # Cross-conversation exact dedup on training set only
    if dedupe_exact:
        train_convs = _dedupe_exact(train_convs, max_copies=max_duplicate_count)

    # Sentence-level dedup on training set
    if dedupe_sentences and filter_sentences:
        train_convs = _dedupe_sentences(train_convs, filter_list=set(filter_sentences))

    # Cross-conversation canned message dedup
    if dedupe_canned:
        train_convs = _dedupe_canned(train_convs, max_copies=max_duplicate_count)

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

    # Save score stats (consumed by run_score.py)
    score_stats_path = output_path / "score_stats.json"
    try:
        with open(score_stats_path, "w") as fh:
            json.dump(summary, fh, ensure_ascii=False)
    except OSError:
        pass  # non-critical, scorer can use inline stats

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


def _dedupe_exact(
    conversations: list[dict[str, Any]],
    max_copies: int = 3,
) -> list[dict[str, Any]]:
    """Remove excessive duplicate messages across conversations.

    For each unique message (normalized), keep at most max_copies
    occurrences. Drops the message entirely from conversations where
    it appears past the limit, removing the turn.

    This prevents model bias from canned/template responses.
    """
    from collections import Counter

    # Count normalized message occurrences
    msg_counts: Counter = Counter()
    for conv in conversations:
        seen_in_conv: set[str] = set()
        for turn in conv["conversation"]:
            norm = " ".join(turn["content"].lower().split())
            if norm not in seen_in_conv:
                msg_counts[norm] += 1
                seen_in_conv.add(norm)

    # Track how many times we've kept each message
    kept: Counter = Counter()
    dropped = 0

    for conv in conversations:
        filtered_turns = []
        for turn in conv["conversation"]:
            norm = " ".join(turn["content"].lower().split())
            if kept[norm] < max_copies:
                kept[norm] += 1
                filtered_turns.append(turn)
            else:
                dropped += 1
        conv["conversation"] = filtered_turns

    if dropped:
        logger.info("Dedupe: dropped %d duplicate message occurrences (keep <=%d)", dropped, max_copies)

    # Drop conversations that became single-turn (system + one user = no agent reply)
    # These are useless for training after their agent responses were deduplicated.
    before_drop = len(conversations)
    conversations = [
        c for c in conversations
        if sum(1 for t in c["conversation"] if t["role"] != "system") >= 2
    ]
    if before_drop > len(conversations):
        logger.info(
            "Dedupe: dropped %d broken conversations (no agent reply after dedup)",
            before_drop - len(conversations),
        )

    # Remove conversations that became empty after dedup
    conversations = [c for c in conversations if len(c["conversation"]) > 0]

    return conversations


def _dedupe_sentences(
    conversations: list[dict[str, Any]],
    filter_list: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Remove over-represented sentences from conversations.

    Uses an explicit filter list (set in config.yaml after analysis).
    Matches any 35-character slice of each filter phrase to handle
    minor wording variants of the same template.

    Only drops sentences from multi-sentence messages; single-sentence
    messages get the template phrase stripped (not dropped).
    """
    if not filter_list:
        return conversations

    # Pre-compute 35-char slices for flexible matching
    filter_slices: list[set[str]] = []
    for f in filter_list:
        slices = {f[i:i + 35] for i in range(0, max(1, len(f) - 35))}
        if slices:
            filter_slices.append(slices)

    if not filter_slices:
        return conversations

    def _matches_filter(text: str) -> bool:
        """Check if text contains any slice of any filter phrase."""
        return any(
            any(slice_ in text for slice_ in slices)
            for slices in filter_slices
        )

    def _safe_replace(body: str, phrase: str) -> str:
        """Replace phrase in body only when at word boundaries.

        Avoids mid-word garbling like "subscription" → "bscription".
        """
        idx = body.find(phrase)
        if idx == -1:
            return body
        body_len = len(body)
        phrase_len = len(phrase)
        at_start = idx <= 2
        at_end = (body_len - (idx + phrase_len)) <= 2
        if not at_start and not at_end:
            return body  # mid-text: don't break words
        before = body[:idx].rstrip()
        after = body[idx + phrase_len:].lstrip()
        return (before + " " + after).strip()

    dropped = 0

    for conv in conversations:
        filtered_turns = []
        for turn in conv["conversation"]:
            sentences = _split_sentences(turn["content"])
            if len(sentences) <= 1:
                # Single sentence: strip matched phrases at boundaries only
                body = turn["content"]
                matched = False
                for slices, original_filter in zip(filter_slices, filter_list):
                    # Try original filter first, then 35-char slices
                    for phrase in [original_filter] + sorted(slices, key=len, reverse=True):
                        if phrase in body:
                            new_body = _safe_replace(body, phrase)
                            if new_body != body:
                                body = new_body
                                matched = True
                                break
                if matched:
                    dropped += 1
                    body = " ".join(body.split()).strip()
                if body:
                    turn["content"] = body
                    filtered_turns.append(turn)
                continue

            kept_sentences = [s for s in sentences if not _matches_filter(s)]
            if kept_sentences:
                dropped += len(sentences) - len(kept_sentences)
                turn["content"] = ". ".join(kept_sentences)
                filtered_turns.append(turn)
            else:
                dropped += len(sentences)
        conv["conversation"] = filtered_turns

    logger.info("Sentence dedup: dropped %d sentence occurrences", dropped)
    conversations = [c for c in conversations if len(c["conversation"]) > 0]
    return conversations


def _analyze_sentences(
    conversations: list[dict[str, Any]],
    top_n: int = 50,
) -> list[tuple[str, int, str]]:
    """Analyze sentence frequencies and return candidates for filtering.

    Returns the top-N most frequent sentences (min 15 chars) as
    (sentence, count, role) tuples sorted by frequency.
    """
    from collections import Counter

    sent_freq: Counter = Counter()
    sent_role: dict[str, str] = {}  # cache role for each sentence
    for conv in conversations:
        for turn in conv["conversation"]:
            role = turn["role"]
            for sent in _split_sentences(turn["content"]):
                if len(sent) > 15:
                    sent_freq[sent] += 1
                    if sent not in sent_role:
                        sent_role[sent] = role

    candidates = [(s, c, sent_role.get(s, "n/a"))
                  for s, c in sent_freq.items() if c > 1]
    candidates.sort(key=lambda x: -x[1])
    return candidates[:top_n]


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences on period and newline boundaries.

    Protects URLs and numeric dots (time formats, version numbers)
    from being split by replacing them with placeholders before
    splitting, then restoring them.
    """
    # Protect numeric dots (time formats, version numbers, decimals)
    # Replace "." between digits with \x00 to prevent dot-splitting
    text = re.sub(r'(\d)\.(\d)', lambda m: m.group(1) + '\x00' + m.group(2), text)

    # Protect URLs: replace . in URLs with placeholder
    url_pattern = re.compile(r'(https?://[^\s]+)')
    placeholders: dict[str, str] = {}
    counter = 0

    def _protect(m: re.Match) -> str:
        nonlocal counter
        key = f'__URL_{counter}__'
        counter += 1
        url = m.group(0)
        # If URL ends with punctuation and next char is whitespace,
        # split the punctuation out — it's a sentence delimiter
        end = m.end()
        while url and url[-1] in '.,;:!?)]' and (end >= len(text) or text[end:end+1] in (' ', '\n', '')):
            url = url[:-1]
            end -= 1
        placeholders[key] = url
        return key

    text = url_pattern.sub(_protect, text)

    parts = []
    for chunk in text.replace("\n", ".").split("."):
        stripped = chunk.strip()
        if stripped:
            # Restore protected URLs
            for key, url in placeholders.items():
                stripped = stripped.replace(key, url)
            # Restore numeric dots
            stripped = stripped.replace('\x00', '.')
            parts.append(stripped)
    return parts


def _dedupe_canned(
    conversations: list[dict[str, Any]],
    max_copies: int = 3,
) -> list[dict[str, Any]]:
    """Limit canned/template messages per-signature across the dataset.

    Dynamically discovers canned signatures via frequency analysis,
    then keeps at most max_copies messages per signature.
    Only drops messages where the canned signature dominates
    (covers >= 60% of the message), preserving specific support
    responses that happen to share common phrases.
    """
    from collections import Counter

    # Phase 1: discover canned signatures dynamically
    signatures = _discover_canned_signatures(conversations)

    if not signatures:
        return conversations

    # Sort signatures by length (longest first) for best match
    sorted_sigs = sorted(signatures, key=len, reverse=True)

    # Phase 2: keep at most max_copies per signature.
    # Messages with canned suffix (<60% coverage) get the suffix stripped
    # instead of being dropped. Messages with canned phrases mid-text get
    # just the phrase stripped.
    kept_per_sig: Counter = Counter()
    dropped = 0
    kept = 0
    stripped = 0

    for conv in conversations:
        filtered_turns = []
        for turn in conv["conversation"]:
            body = turn["content"]
            sig = _longest_matching_sig(body, sorted_sigs)

            if sig is None:
                filtered_turns.append(turn)
                continue

            fraction = len(sig) / max(len(" ".join(body.split())), 1)

            if fraction >= 0.6:
                # Template dominates: keep max_copies, drop rest
                if kept_per_sig[sig] < max_copies:
                    kept_per_sig[sig] += 1
                    kept += 1
                    filtered_turns.append(turn)
                else:
                    dropped += 1
            else:
                # Strip the canned phrase from the message
                new_body = _remove_canned_phrase(body, sig)
                if new_body and len(new_body) >= 3:
                    turn["content"] = new_body
                    stripped += 1
                    filtered_turns.append(turn)
                else:
                    dropped += 1
        conv["conversation"] = filtered_turns

    logger.info(
        "Canned dedup: kept %d, dropped %d, stripped %d messages",
        kept, dropped, stripped,
    )
    conversations = [c for c in conversations if len(c["conversation"]) > 0]
    return conversations


def _remove_canned_phrase(body: str, sig: str) -> str | None:
    """Remove a canned signature phrase from a message.

    Only removes when the signature appears at the beginning or end
    of the message (within 10 chars of either boundary). Mid-message
    occurrences are part of natural content and should not be stripped
    — blind replacement breaks words (e.g., "subscription" → "bscription").
    """
    normalized = " ".join(body.split())
    idx = normalized.find(sig)
    if idx == -1:
        return body

    body_len = len(normalized)
    sig_len = len(sig)

    # Only strip if at the beginning (idx <= 10) or end (remaining < 10)
    at_start = idx <= 10
    at_end = (body_len - (idx + sig_len)) < 10

    if not at_start and not at_end:
        return body  # mid-message: keep intact

    result = normalized[:idx] + " " + normalized[idx + sig_len:]
    result = " ".join(result.split())
    result = result.strip().rstrip(",;:!?。，；：！？")
    return result if result else None


def _longest_matching_sig(body: str, sorted_sigs: list[str]) -> str | None:
    """Return the longest canned signature found in body, or None."""
    normalized = " ".join(body.split())
    for sig in sorted_sigs:
        if sig in normalized:
            return sig
    return None
