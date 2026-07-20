"""Zendesk Ticket Exporter — exports Facebook Messenger tickets with full conversations.

Uses Zendesk Search API for fast date-range discovery (100 tickets/page) plus
the Comments API per ticket to fetch full conversation history.

Functional Requirements:
  FR-001: Export ticket metadata
  FR-002: Export ticket comments (full conversation)
  FR-003: Date-range export (Search API) + ongoing sync (Incremental API)
  FR-004: Retry when rate limited
  FR-005: Save one JSON file per ticket
  FR-006: Store all public comments
  FR-007: Support resume after interruption
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
        raise ValueError("ZENDESK_SUBDOMAIN is not set in .env or config.")
    return f"https://{subdomain}.zendesk.com/api/v2{path}"


def _auth(cfg: dict[str, Any]) -> tuple[str, str]:
    return (f"{cfg['email']}/token", cfg["api_token"])


def _parse_date(datestr: str | None) -> int | None:
    """Convert ISO date string to Unix timestamp. Returns None if empty."""
    if not datestr:
        return None
    dt = datetime.fromisoformat(datestr)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


# ---------------------------------------------------------------
# Checkpoint (resume) support — FR-007
# ---------------------------------------------------------------


def _load_checkpoint(checkpoint_path: Path) -> dict[str, Any]:
    """Read checkpoint dict. Returns empty dict if absent/corrupt."""
    if checkpoint_path.exists():
        try:
            return json.loads(checkpoint_path.read_text())
        except (json.JSONDecodeError, KeyError):
            logger.warning("Corrupt checkpoint; starting fresh.")
    return {}


def _save_checkpoint(checkpoint_path: Path, data: dict[str, Any]) -> None:
    """Persist checkpoint state."""
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_text(json.dumps(data))


# ---------------------------------------------------------------
# Search API — find tickets in date range
# ---------------------------------------------------------------


def _search_tickets(
    session: requests.Session,
    cfg: dict[str, Any],
    start_date: str,
    end_date: str | None,
    channel_id: str,
    per_page: int = 100,
) -> list[dict[str, Any]]:
    """Use Zendesk Search API to find tickets by channel and date range.

    Much faster than Incremental API for date-range exports (100 tickets/page).
    Handles the 1000-result Search API cap by auto-splitting the date range.
    """
    tickets = _search_tickets_page(
        session, cfg, start_date, end_date, channel_id, per_page,
    )

    # Zendesk Search API caps at 1000 results. If we hit the cap,
    # split the date range in half and search each half recursively.
    if len(tickets) >= 1000:
        logger.warning(
            "Hit 1000-result Search API cap (%s → %s). Splitting date range...",
            start_date, end_date or "now",
        )
        middle = _split_date_range(start_date, end_date)
        if middle is None:
            logger.warning("Date range is a single day — cannot split further.")
            return tickets

        logger.info("Split into [%s → %s) and [%s → %s]",
                     start_date, middle, middle, end_date or "now")
        first = _search_tickets(session, cfg, start_date, middle, channel_id, per_page)
        second = _search_tickets(session, cfg, middle, end_date, channel_id, per_page)
        tickets = first + second
        logger.info("Split search complete: %d total tickets", len(tickets))

    return tickets


def _split_date_range(start: str, end: str | None) -> str | None:
    """Return the midpoint date between start and end, or None if same day."""
    from datetime import timedelta

    s = datetime.fromisoformat(start)
    if end is None:
        e = datetime.now(timezone.utc)
    else:
        e = datetime.fromisoformat(end)

    diff = (e - s).days
    if diff < 2:
        return None  # can't split further

    middle = s + timedelta(days=diff // 2)
    return middle.strftime("%Y-%m-%d")


def _search_tickets_page(
    session: requests.Session,
    cfg: dict[str, Any],
    start_date: str,
    end_date: str | None,
    channel_id: str,
    per_page: int,
) -> list[dict[str, Any]]:
    # Build search query with ISO date strings (not Unix timestamps)
    query_parts = ["type:ticket", f"via:{channel_id}"]
    query_parts.append(f"created>={start_date}")
    if end_date:
        query_parts.append(f"created<={end_date}")

    query = " ".join(query_parts)
    url = _api_url(cfg, "/search.json")
    auth = _auth(cfg)
    params: dict[str, Any] = {
        "query": query,
        "per_page": per_page,
        "sort_by": "created_at",
        "sort_order": "asc",
    }

    all_tickets: list[dict[str, Any]] = []
    page = 0
    next_url: str | None = url

    while next_url:
        page += 1
        if page == 1:
            resp = session.get(url, auth=auth, params=params, timeout=30)
        else:
            resp = session.get(next_url, auth=auth, timeout=30)

        # Zendesk Search API caps at 1000 results — page 11+ returns 422.
        # Catch it gracefully so the caller can split the date range.
        if resp.status_code == 422 and page > 10:
            logger.debug(
                "Search page %d: 422 (likely 1000-result cap), stopping pagination",
                page,
            )
            break

        resp.raise_for_status()
        data = resp.json()

        results = data.get("results", [])
        all_tickets.extend(results)
        logger.info(
            "Search page %d: %d tickets found (total: %d)",
            page, len(results), len(all_tickets),
        )

        next_url = data.get("next_page")

    return all_tickets


# ---------------------------------------------------------------
# Comments API — fetch full conversation per ticket
# ---------------------------------------------------------------


def _fetch_comments(
    session: requests.Session,
    cfg: dict[str, Any],
    ticket_id: int,
) -> list[dict[str, Any]]:
    """Fetch all comments for a single ticket — FR-002, FR-006."""
    url = _api_url(cfg, f"/tickets/{ticket_id}/comments.json")
    auth = _auth(cfg)
    params: dict[str, Any] = {"per_page": 100}

    all_comments: list[dict[str, Any]] = []
    next_url: str | None = url

    while next_url:
        if next_url == url:
            resp = session.get(url, auth=auth, params=params, timeout=30)
        else:
            resp = session.get(next_url, auth=auth, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        comments = data.get("comments", [])
        all_comments.extend(comments)

        next_url = data.get("next_page")

    return all_comments


# ---------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------


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
    }


def _format_comment(comment: dict[str, Any]) -> dict[str, Any]:
    """Format a single comment — FR-002, FR-006."""
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


def _ticket_to_json(
    ticket: dict[str, Any],
    comments: list[dict[str, Any]],
) -> dict[str, Any]:
    """Convert a raw Zendesk ticket + comments to structured JSON."""
    return {
        "ticket_id": ticket.get("id"),
        "metadata": _extract_fields(ticket),
        "channel": "facebook_messenger",
        "comments": [
            _format_comment(c)
            for c in sorted(comments, key=lambda c: c.get("created_at", ""))
        ],
    }


def _save_ticket(ticket_json: dict[str, Any], output_dir: Path) -> Path:
    """Persist one ticket as JSON — FR-005."""
    ticket_id = ticket_json["ticket_id"]
    output_path = output_dir / f"ticket_{ticket_id}.json"
    output_path.write_text(
        json.dumps(ticket_json, ensure_ascii=False, indent=2)
    )
    return output_path


# ---------------------------------------------------------------
# Main export orchestrator
# ---------------------------------------------------------------


def run_export(
    config_path: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """Export Zendesk Facebook Messenger tickets with full conversations.

    1. Search API: find all Facebook Messenger tickets in date range (fast, 100/page)
    2. Comments API: fetch full conversation for each ticket (concurrent, 5 at a time)
    3. Save each as ticket_{id}.json

    Args:
        config_path: Optional override for config YAML.
        start_date: ISO date string (e.g. "2024-01-01").
        end_date: ISO date string.

    Returns:
        Summary dict with counts and status.
    """
    cfg = get_export_config()
    if config_path:
        from src.common.config import load_config
        cfg = load_config(config_path).get("export", {})

    # Validate credentials
    if not cfg.get("subdomain") or not cfg.get("email") or not cfg.get("api_token"):
        logger.error("Missing Zendesk credentials.")
        return {"error": "missing_credentials", "tickets_exported": 0}

    # Resolve dates
    if not start_date and cfg.get("start_time"):
        start_date = cfg["start_time"]
    if not end_date and cfg.get("end_time"):
        end_date = cfg["end_time"]

    if not start_date:
        logger.error(
            "start_date is required. Use --start-date or set export.start_time in config."
        )
        return {"error": "missing_start_date", "tickets_exported": 0}

    channel_id = cfg.get("channel_id", "sunshine_conversations_facebook_messenger")

    output_dir = Path(cfg.get("output_dir", "data/raw"))
    output_dir.mkdir(parents=True, exist_ok=True)

    checkpoint_path = Path(cfg.get("checkpoint_file", "data/export_cursor.json"))
    concurrency = cfg.get("comment_concurrency", 5)

    logger.info("Export: %s → %s | channel: %s", start_date, end_date or "now", channel_id)

    # ----- Phase 1: Search for tickets -----
    session = _build_session(
        max_retries=cfg.get("max_retries", 5),
        backoff_base=cfg.get("retry_backoff_base", 2),
    )

    logger.info("Phase 1: Searching for tickets via %s...", channel_id)
    t0 = time.time()

    try:
        tickets = _search_tickets(session, cfg, start_date, end_date, channel_id)
    except requests.HTTPError as exc:
        logger.error("Search API error: %s", exc)
        return {"error": "search_api_error", "tickets_exported": 0}

    if not tickets:
        logger.info("No Facebook Messenger tickets found in date range.")
        return {
            "tickets_exported": 0,
            "tickets_found": 0,
            "elapsed_seconds": round(time.time() - t0, 1),
            "output_dir": str(output_dir),
        }

    logger.info(
        "Found %d tickets in %.1fs. Phase 2: fetching comments...",
        len(tickets), time.time() - t0,
    )

    # ----- Phase 2: Fetch comments concurrently -----
    t1 = time.time()
    tickets_exported = 0
    tickets_failed = 0

    # FR-007: Resume — load already-exported ticket IDs
    checkpoint = _load_checkpoint(checkpoint_path)
    done_ids: set[int] = set(checkpoint.get("done_ticket_ids", []))

    # Sort tickets chronologically
    tickets.sort(key=lambda t: t.get("created_at", ""))

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        # Submit all comment fetch jobs
        futures: dict[Any, dict[str, Any]] = {}
        for ticket in tickets:
            tid = ticket["id"]
            if tid in done_ids:
                logger.debug("Skipping ticket %d (already exported)", tid)
                continue
            future = executor.submit(
                _fetch_and_save,
                session, cfg, ticket, output_dir, checkpoint_path, done_ids,
            )
            futures[future] = ticket

        # Collect results
        for future in as_completed(futures):
            ticket = futures[future]
            tid = ticket["id"]
            try:
                success = future.result()
                if success:
                    tickets_exported += 1
                    done_ids.add(tid)
                else:
                    tickets_failed += 1
            except Exception as exc:
                logger.error("Ticket %d failed: %s", tid, exc)
                tickets_failed += 1

            # Progress every 10 tickets
            total_done = tickets_exported + tickets_failed + len(done_ids)
            if total_done % 10 == 0:
                elapsed = time.time() - t1
                rate = tickets_exported / elapsed if elapsed > 0 else 0
                remaining = len(tickets) - tickets_exported - tickets_failed - len(done_ids)
                logger.info(
                    "Comments: %d/%d exported | %.1f/sec | %d remaining",
                    tickets_exported, len(tickets), rate, max(0, remaining),
                )

        # Final checkpoint save
        _save_checkpoint(checkpoint_path, {"done_ticket_ids": list(done_ids)})

    elapsed = time.time() - t0
    logger.info(
        "Export done: %d tickets exported, %d failed in %.0fs (%.1f/sec)",
        tickets_exported, tickets_failed, elapsed,
        tickets_exported / elapsed if elapsed > 0 else 0,
    )

    # Clear checkpoint on full success
    if tickets_failed == 0:
        _save_checkpoint(checkpoint_path, {})

    return {
        "tickets_exported": tickets_exported,
        "tickets_failed": tickets_failed,
        "tickets_found": len(tickets),
        "elapsed_seconds": round(elapsed, 1),
        "output_dir": str(output_dir),
    }


def _fetch_and_save(
    session: requests.Session,
    cfg: dict[str, Any],
    ticket: dict[str, Any],
    output_dir: Path,
    checkpoint_path: Path,
    done_ids: set[int],
) -> bool:
    """Fetch comments for a single ticket and save the result. Returns True on success."""
    tid = ticket["id"]
    try:
        comments = _fetch_comments(session, cfg, tid)
        ticket_json = _ticket_to_json(ticket, comments)
        _save_ticket(ticket_json, output_dir)
        return True
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            logger.warning("Ticket %d: 404 (may be deleted), skipping", tid)
        else:
            logger.error("Ticket %d: HTTP %s", tid, exc)
        return False
