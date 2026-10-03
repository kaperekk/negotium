"""
context.py — project workspace and path context resolution.

Encapsulates data root, project layout, and multi-tenant project resolution
without leaking global state into computation engines.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).parent.parent.parent
DATA_ROOT = ROOT / "data"
COMMON_ROOT = DATA_ROOT / "common"
USERS_ROOT = DATA_ROOT / "users"

_SESSION_PROJECT_KEY = "negotium_current_project"
_SESSION_USER_KEY = "negotium_user_id"
_current_project: str | None = None
_current_user: str | None = None


def get_current_project() -> str | None:
    """Return the active project: session-scoped first, then process fallback."""
    try:
        import streamlit as st
        val = st.session_state.get(_SESSION_PROJECT_KEY)
        if val:
            return str(val)
    except Exception:
        pass  # no Streamlit runtime (tests, plain scripts) -> process fallback
    return _current_project


def set_current_project(name: str | None) -> None:
    """Set the active project for this session (and the process fallback)."""
    global _current_project
    _current_project = name
    try:
        import streamlit as st
        if name is not None:
            st.session_state[_SESSION_PROJECT_KEY] = name
        else:
            st.session_state.pop(_SESSION_PROJECT_KEY, None)
    except Exception:
        pass


def get_current_user() -> str | None:
    """Return the authenticated user_id from session."""
    try:
        import streamlit as st
        val = st.session_state.get(_SESSION_USER_KEY)
        if val:
            return str(val)
    except Exception:
        pass
    return _current_user


def set_current_user(user_id: str | None) -> None:
    """Set the authenticated user for this session."""
    global _current_user
    _current_user = user_id
    try:
        import streamlit as st
        if user_id is not None:
            st.session_state[_SESSION_USER_KEY] = user_id
        else:
            st.session_state.pop(_SESSION_USER_KEY, None)
    except Exception:
        pass


def get_user_data_root(user_id: str | None = None) -> Path:
    """Get the data root for a specific user (creates if needed)."""
    uid = user_id or get_current_user()
    if not uid:
        raise RuntimeError("No authenticated user. Call set_current_user() first.")
    user_dir = USERS_ROOT / uid
    user_dir.mkdir(parents=True, exist_ok=True)
    (user_dir / "projects").mkdir(parents=True, exist_ok=True)
    return user_dir


def get_common_root() -> Path:
    """Get the shared common data root (prices, metadata)."""
    COMMON_ROOT.mkdir(parents=True, exist_ok=True)
    (COMMON_ROOT / "prices").mkdir(parents=True, exist_ok=True)
    (COMMON_ROOT / "prices_adj").mkdir(parents=True, exist_ok=True)
    (COMMON_ROOT / "dividends").mkdir(parents=True, exist_ok=True)
    return COMMON_ROOT


class ProjectContext:
    """Encapsulates file paths and directory layout for a given project."""

    def __init__(self, name: str | None = None, data_root: Path | None = None):
        self._name = name
        self._data_root = data_root

    @property
    def data_root(self) -> Path:
        import storage
        if self._data_root:
            return self._data_root
        # Use user-specific data root if authenticated, else fall back to global
        try:
            return get_user_data_root()
        except RuntimeError:
            return getattr(storage, "DATA_ROOT", DATA_ROOT)

    @data_root.setter
    def data_root(self, val: Path) -> None:
        self._data_root = val

    @property
    def name(self) -> str:
        n = self._name or get_current_project()
        if n is None:
            raise RuntimeError("No project selected. Call set_current_project() or provide project name.")
        return n

    @property
    def project_dir(self) -> Path:
        return self.data_root / self.name

    @property
    def transactions_path(self) -> Path:
        return self.project_dir / "transactions.jsonl"

    @property
    def portfolio_path(self) -> Path:
        return self.project_dir / "portfolio.jsonl"

    @property
    def balance_path(self) -> Path:
        return self.project_dir / "balance.json"

    @property
    def imports_dir(self) -> Path:
        return self.project_dir / "imports"

    def benchmark_cache_path(self, base_ccy: str) -> Path:
        return self.project_dir / f"benchmarks_{base_ccy.upper()}.json"

    def ensure_directories(self) -> None:
        self.project_dir.mkdir(parents=True, exist_ok=True)
        self.imports_dir.mkdir(parents=True, exist_ok=True)
