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
        allowed_methods=["GET", "POST", "PUT", "DELETE"],
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
            "ZENDESK_SUBDOMAIN is not set in .env or config. "
            "Set it before running the exporter."
        )
    return f"https://{subdomain}.zendesk.com/api/v2{path}"


# ---------------------------------------------------------------
# Checkpoint (resume) support  — FR-007
# ---------------------------------------------------------------


def _load_cursor(checkpoint_path: Path) -> int | None:
    """Read persisted cursor from checkpoint file. Returns None if absent."""
    if checkpoint_path.exists():
        try:
            data = json.loads(checkpoint_path.read_text())
            return data.get("cursor")
        except (json.JSONDecodeError, KeyError):
            logger.warning("Corrupt checkpoint file; starting fresh.")
    return None


def _save_cursor(checkpoint_path: Path, cursor: int | None) -> None:
    """Persist cursor for resume."""
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_text(json.dumps({"cursor": cursor}))


# ---------------------------------------------------------------
# Incremental Export — FR-001, FR-002, FR-003
# ---------------------------------------------------------------


def _fetch_tickets_page(
    session: requests.Session,
    cfg: dict[str, Any],
    start_time: int | None = None,
) -> dict[str, Any]:
    """Fetch a page of tickets from the Zendesk Incremental Tickets API.

    Args:
        session: requests Session with retry logic.
        cfg: Export config dict.
        start_time: Unix timestamp for the start_time parameter.

    Returns:
        API response JSON as dict.
    """
    params: dict[str, Any] = {}
    if start_time is not None:
        params["start_time"] = start_time
    else:
        params["start_time"] = int(time.time()) - 3600  # default: last hour

    url = _api_url(cfg, "/incremental/tickets.json")
    auth = (f"{cfg['email']}/token", cfg["api_token"])

    logger.info("Fetching tickets page, start_time=%s", start_time)
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
        "channel": "facebook_messenger",  # MVP: Facebook Messenger only
        "comments": [
            _format_comment(c)
            for c in sorted(
                ticket.get("comments", []),
                key=lambda c: c.get("created_at", ""),
            )
        ],
    }


def _save_ticket(ticket_json: dict[str, Any], output_dir: Path) -> Path:
    """Persist one ticket as JSON — FR-005."""
    ticket_id = ticket_json["ticket_id"]
    output_path = output_dir / f"ticket_{ticket_id}.json"
    output_path.write_text(json.dumps(ticket_json, ensure_ascii=False, indent=2))
    return output_path


# ---------------------------------------------------------------
# Main export orchestrator
# ---------------------------------------------------------------


def run_export(config_path: str | None = None) -> dict[str, Any]:
    """Execute the Zendesk incremental export.

    Args:
        config_path: Optional override path to config YAML.

    Returns:
        Summary dict with counts and status.
    """
    cfg = get_export_config()
    # Reload full config if path overridden
    if config_path:
        from src.common.config import load_config

        full_cfg = load_config(config_path)
        cfg = full_cfg.get("export", {})

    # Validate credentials
    if not cfg.get("subdomain") or not cfg.get("email") or not cfg.get("api_token"):
        logger.error(
            "Missing Zendesk credentials. Set ZENDESK_SUBDOMAIN, ZENDESK_EMAIL, "
            "ZENDESK_API_TOKEN in .env"
        )
        return {"error": "missing_credentials", "tickets_exported": 0}

    output_dir = Path(cfg.get("output_dir", "data/raw"))
    output_dir.mkdir(parents=True, exist_ok=True)

    checkpoint_path = Path(cfg.get("checkpoint_file", "data/export_cursor.json"))

    # FR-007: Resume from checkpoint
    start_time = _load_cursor(checkpoint_path)
    if start_time:
        logger.info("Resuming export from cursor: %s", start_time)

    session = _build_session(
        max_retries=cfg.get("max_retries", 5),
        backoff_base=cfg.get("retry_backoff_base", 2),
    )

    tickets_exported = 0
    next_start_time: int | None = None
    pages = 0

    while True:
        pages += 1
        try:
            data = _fetch_tickets_page(session, cfg, start_time=start_time)
        except requests.HTTPError as exc:
            logger.error("HTTP error on page %d: %s", pages, exc)
            return {
                "error": f"http_error_page_{pages}",
                "tickets_exported": tickets_exported,
                "last_cursor": start_time,
            }

        tickets = data.get("tickets", [])
        logger.info("Page %d: %d tickets received", pages, len(tickets))

        for raw_ticket in tickets:
            ticket_json = _ticket_to_json(raw_ticket)
            _save_ticket(ticket_json, output_dir)
            tickets_exported += 1

        # FR-003: Use next_page for cursor progression
        next_page_url = data.get("next_page")
        if not next_page_url:
            logger.info("No more pages. Export complete.")
            break

        # Extract start_time from next_page URL for checkpoint
        import urllib.parse as urlparse

        parsed = urlparse.urlparse(next_page_url)
        qs = urlparse.parse_qs(parsed.query)
        next_start_time = int(qs.get("start_time", [0])[0])

        # FR-007: Persist cursor after each page
        _save_cursor(checkpoint_path, next_start_time)
        start_time = next_start_time

    # Clear checkpoint on successful completion
    _save_cursor(checkpoint_path, None)
    logger.info("Export finished: %d tickets across %d pages", tickets_exported, pages)

    return {
        "tickets_exported": tickets_exported,
        "pages": pages,
        "output_dir": str(output_dir),
    }
