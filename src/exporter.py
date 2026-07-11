"""Zendesk Incremental Export — exports Facebook Messenger tickets to raw JSON files.

Functional Requirements:
  FR-001: Export ticket metadata
  FR-002: Export ticket comments
  FR-003: Support Incremental Export API
  FR-004: Retry when rate limited
  FR-005: Save one JSON file per ticket
  FR-006: Store all public comments
  FR-007: Support resume after interruption
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.common.config import get_export_config
from src.common.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------
# Rate-limit retry session
# ---------------------------------------------------------------


def _build_session(max_retries: int, backoff_base: float) -> requests.Session:
    """Create a requests Session with exponential backoff on 429/5xx."""
    retry_strategy = Retry(
        total=max_retries,
        backoff_factor=backoff_base,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _api_url(cfg: dict[str, Any], path: str) -> str:
    """Build a fully-qualified Zendesk API URL."""
    subdomain = cfg["subdomain"]
    if not subdomain:
        raise ValueError(
            "ZENDESK_SUBDOMAIN is not set in .env or config."
        )
    return f"https://{subdomain}.zendesk.com/api/v2{path}"


def _parse_date(datestr: str | None) -> int | None:
    """Convert ISO date string to Unix timestamp. Returns None if empty."""
    if not datestr:
        return None
    dt = datetime.fromisoformat(datestr)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


# ---------------------------------------------------------------
# Checkpoint (resume) support  — FR-007
# ---------------------------------------------------------------


def _load_cursor(checkpoint_path: Path) -> str | None:
    """Read persisted next_page URL from checkpoint. Returns None if absent."""
    if checkpoint_path.exists():
        try:
            data = json.loads(checkpoint_path.read_text())
            return data.get("next_page_url")
        except (json.JSONDecodeError, KeyError):
            logger.warning("Corrupt checkpoint file; starting fresh.")
    return None


def _save_cursor(checkpoint_path: Path, next_page_url: str | None) -> None:
    """Persist next_page URL for resume."""
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_text(json.dumps({"next_page_url": next_page_url}))


# ---------------------------------------------------------------
# Incremental Export — FR-001, FR-002, FR-003
# ---------------------------------------------------------------


def _fetch_tickets_page(
    session: requests.Session,
    cfg: dict[str, Any],
    start_time: int | None = None,
    next_page_url: str | None = None,
) -> dict[str, Any]:
    """Fetch a page of tickets from the Zendesk Incremental Tickets API.

    On the first call, pass `start_time` (Unix timestamp). On subsequent
    calls, pass `next_page_url` — we follow the server-provided URL directly
    to preserve Zendesk's pagination cursor.
    """
    auth = (f"{cfg['email']}/token", cfg["api_token"])

    if next_page_url:
        # Follow the exact next_page URL from Zendesk (preserves cursor state)
        logger.debug("Following next_page URL")
        resp = session.get(next_page_url, auth=auth, timeout=60)
    else:
        url = _api_url(cfg, "/incremental/tickets.json")
        params: dict[str, Any] = {}
        if start_time is not None:
            params["start_time"] = start_time
        else:
            params["start_time"] = int(time.time()) - 3600
        resp = session.get(url, auth=auth, params=params, timeout=60)

    resp.raise_for_status()
    return resp.json()


def _extract_fields(ticket: dict[str, Any]) -> dict[str, Any]:
    """Extract key metadata fields from a ticket — FR-001."""
    return {
        "id": ticket.get("id"),
        "subject": ticket.get("subject"),
        "status": ticket.get("status"),
        "created_at": ticket.get("created_at"),
        "updated_at": ticket.get("updated_at"),
        "requester_id": ticket.get("requester_id"),
        "submitter_id": ticket.get("submitter_id"),
        "assignee_id": ticket.get("assignee_id"),
        "group_id": ticket.get("group_id"),
        "tags": ticket.get("tags", []),
        "custom_fields": ticket.get("custom_fields", []),
    }


def _format_comment(comment: dict[str, Any]) -> dict[str, Any]:
    """Format a single comment — FR-002, FR-006 (public only)."""
    return {
        "id": comment.get("id"),
        "author_id": comment.get("author_id"),
        "created_at": comment.get("created_at"),
        "public": comment.get("public", True),
        "body": comment.get("body", ""),
        "attachments": [
            {
                "file_name": att.get("file_name"),
                "content_url": att.get("content_url"),
            }
            for att in comment.get("attachments", [])
        ],
    }


def _ticket_to_json(ticket: dict[str, Any]) -> dict[str, Any]:
    """Convert a raw Zendesk ticket to our structured JSON schema."""
    return {
        "ticket_id": ticket.get("id"),
        "metadata": _extract_fields(ticket),
        "channel": "facebook_messenger",
        "comments": [
            _format_comment(c)
            for c in sorted(
                ticket.get("comments", []),
                key=lambda c: c.get("created_at", ""),
            )
        ],
    }


def _ticket_past_end(ticket: dict[str, Any], end_time: int | None) -> bool:
    """Return True if the ticket's updated_at is past the end_time cutoff."""
    if end_time is None:
        return False
    updated = ticket.get("updated_at", "")
    if not updated:
        return False
    try:
        dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
        return int(dt.timestamp()) > end_time
    except (ValueError, TypeError):
        return False


def _save_ticket(ticket_json: dict[str, Any], output_dir: Path) -> Path:
    """Persist one ticket as JSON — FR-005."""
    ticket_id = ticket_json["ticket_id"]
    output_path = output_dir / f"ticket_{ticket_id}.json"
    output_path.write_text(json.dumps(ticket_json, ensure_ascii=False, indent=2))
    return output_path


# ---------------------------------------------------------------
# Main export orchestrator
# ---------------------------------------------------------------


def run_export(
    config_path: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """Execute the Zendesk incremental export.

    Args:
        config_path: Optional override path to config YAML.
        start_date: ISO date string (e.g., "2024-01-01") — overrides config.
        end_date: ISO date string — stop exporting tickets past this date.

    Returns:
        Summary dict with counts and status.
    """
    cfg = get_export_config()
    if config_path:
        from src.common.config import load_config

        full_cfg = load_config(config_path)
        cfg = full_cfg.get("export", {})

    # Validate credentials
    if not cfg.get("subdomain") or not cfg.get("email") or not cfg.get("api_token"):
        logger.error("Missing Zendesk credentials.")
        return {"error": "missing_credentials", "tickets_exported": 0}

    output_dir = Path(cfg.get("output_dir", "data/raw"))
    output_dir.mkdir(parents=True, exist_ok=True)

    checkpoint_path = Path(cfg.get("checkpoint_file", "data/export_cursor.json"))

    # Resolve start_time: CLI arg > config > checkpoint > default
    start_time: int | None = None
    if start_date:
        start_time = _parse_date(start_date)
        logger.info("Using CLI start_date: %s → %s", start_date, start_time)
    elif cfg.get("start_time"):
        start_time = _parse_date(cfg["start_time"])
        logger.info("Using config start_time: %s", start_time)

    end_time: int | None = None
    if end_date:
        end_time = _parse_date(end_date)
        logger.info("End date cutoff: %s → %s", end_date, end_time)
    elif cfg.get("end_time"):
        end_time = _parse_date(cfg["end_time"])

    # FR-007: Resume from checkpoint (next_page URL)
    next_page_url = _load_cursor(checkpoint_path)
    if next_page_url:
        logger.info("Resuming from checkpoint (next_page URL)")
    elif start_time is None:
        start_time = int(time.time()) - 3600
        logger.info("No start date given, defaulting to last hour")

    session = _build_session(
        max_retries=cfg.get("max_retries", 5),
        backoff_base=cfg.get("retry_backoff_base", 2),
    )

    tickets_exported = 0
    tickets_skipped = 0
    pages = 0
    max_pages = cfg.get("max_pages", 5000)

    # Progress tracking
    progress_interval = max(1, cfg.get("progress_interval", 50))
    start_wall = time.time()
    last_progress = start_wall

    while pages < max_pages:
        pages += 1
        try:
            data = _fetch_tickets_page(
                session, cfg,
                start_time=start_time,
                next_page_url=next_page_url if pages > 1 else None,
            )
        except requests.HTTPError as exc:
            logger.error("HTTP error on page %d: %s", pages, exc)
            return {
                "error": f"http_error_page_{pages}",
                "tickets_exported": tickets_exported,
                "tickets_skipped": tickets_skipped,
            }

        tickets = data.get("tickets", [])
        page_count = len(tickets)

        for raw_ticket in tickets:
            # Client-side end_date filtering
            if _ticket_past_end(raw_ticket, end_time):
                tickets_skipped += 1
                continue

            ticket_json = _ticket_to_json(raw_ticket)
            _save_ticket(ticket_json, output_dir)
            tickets_exported += 1

        # Progress reporting
        now = time.time()
        if pages % progress_interval == 0 or (now - last_progress) > 30:
            elapsed = now - start_wall
            rate = tickets_exported / elapsed if elapsed > 0 else 0
            logger.info(
                "Page %d | %d exported (+%d this page) | %.1f tickets/sec | %.0fs elapsed",
                pages, tickets_exported, page_count, rate, elapsed,
            )
            last_progress = now

        # Check for next page
        next_page_url = data.get("next_page")
        if not next_page_url:
            logger.info("No more pages. Export complete.")
            break

        # FR-007: Persist checkpoint after each page
        _save_cursor(checkpoint_path, next_page_url)

        # Safety: if end_time is set and ALL tickets on this page were past
        # end, we're done (incremental API returns in chronological order)
        if end_time and page_count > 0 and tickets_skipped > 0 and tickets_exported == 0:
            # Check if even the first ticket is past end
            if _ticket_past_end(tickets[0], end_time):
                logger.info("All tickets past end_date cutoff. Stopping.")
                break

    # Clear checkpoint on successful completion
    _save_cursor(checkpoint_path, None)

    elapsed = time.time() - start_wall
    logger.info(
        "Export finished: %d tickets across %d pages in %.0fs (%.1f/sec)",
        tickets_exported, pages, elapsed,
        tickets_exported / elapsed if elapsed > 0 else 0,
    )

    return {
        "tickets_exported": tickets_exported,
        "tickets_skipped": tickets_skipped,
        "pages": pages,
        "elapsed_seconds": round(elapsed, 1),
        "output_dir": str(output_dir),
    }
