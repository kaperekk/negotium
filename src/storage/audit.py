"""
Audit logging for security-relevant events.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from storage.backends import get_backend

_AUDIT_KEY = "audit.log"
_lock = threading.Lock()


def _audit_backend():
    return get_backend()


def log_event(event_type: str, user: str | None, details: dict[str, Any]) -> None:
    """Log an audit event."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "user": user,
        "details": details,
    }
    backend = _audit_backend()
    # Append to audit log (JSONL format)
    existing = ""
    if backend.exists(_AUDIT_KEY):
        existing = backend.read_bytes(_AUDIT_KEY).decode()
    new_content = existing + json.dumps(entry, ensure_ascii=False) + "\n"
    backend.write_bytes(_AUDIT_KEY, new_content.encode())


def log_login_attempt(user_key: str, success: bool, username: str | None = None) -> None:
    """Log a login attempt."""
    log_event(
        "login_attempt",
        username,
        {
            "user_key_prefix": user_key[:8] + "..." if len(user_key) > 8 else user_key,
            "success": success,
        },
    )


def log_user_created(username: str, user_key: str) -> None:
    """Log user creation."""
    log_event(
        "user_created",
        username,
        {"user_key_prefix": user_key[:8] + "..."},
    )


def log_user_deleted(username: str) -> None:
    """Log user deletion."""
    log_event("user_deleted", username, {})


def log_project_created(project_name: str, user: str) -> None:
    """Log project creation."""
    log_event("project_created", user, {"project_name": project_name})


def log_project_deleted(project_name: str, user: str) -> None:
    """Log project deletion."""
    log_event("project_deleted", user, {"project_name": project_name})


def log_project_renamed(old_name: str, new_name: str, user: str) -> None:
    """Log project rename."""
    log_event("project_renamed", user, {"old_name": old_name, "new_name": new_name})


def log_data_import(project_name: str, user: str, importer: str, records: int) -> None:
    """Log data import."""
    log_event("data_import", user, {"project_name": project_name, "importer": importer, "records": records})


def get_audit_log(limit: int = 100) -> list[dict]:
    """Get recent audit log entries."""
    backend = _audit_backend()
    if not backend.exists(_AUDIT_KEY):
        return []
    content = backend.read_bytes(_AUDIT_KEY).decode()
    lines = content.strip().split("\n")
    entries = [json.loads(line) for line in lines[-limit:] if line.strip()]
    return list(reversed(entries))