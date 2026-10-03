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
USERS_ROOT = DATA_ROOT / "users"
DEFAULT_USER = "default_user"

_SESSION_PROJECT_KEY = "negotium_current_project"
_SESSION_USER_KEY = "negotium_current_user"
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
        pass
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


def get_current_user() -> str:
    """Return the active user: session-scoped first, then process fallback, then default."""
    try:
        import streamlit as st
        val = st.session_state.get(_SESSION_USER_KEY)
        if val:
            return str(val)
    except Exception:
        pass
    return _current_user or DEFAULT_USER


def set_current_user(name: str | None) -> None:
    """Set the active user for this session (and the process fallback)."""
    global _current_user
    _current_user = name
    try:
        import streamlit as st
        if name is not None:
            st.session_state[_SESSION_USER_KEY] = name
            _ensure_user_dir(name)
        else:
            st.session_state.pop(_SESSION_USER_KEY, None)
    except Exception:
        pass


def _ensure_user_dir(name: str) -> None:
    """Ensure user directory exists (for local backend)."""
    from storage.backends import get_backend
    backend = get_backend()
    user_prefix = f"users/{name}/"
    if not backend.exists(user_prefix):
        backend.mkdir(user_prefix)


def get_user_root(user: str | None = None) -> Path:
    """Get the root directory for a specific user (local path for backward compat)."""
    return USERS_ROOT / (user or get_current_user())


def get_user_prefix(user: str | None = None) -> str:
    """Get the storage prefix for a specific user."""
    return f"users/{user or get_current_user()}/"


class ProjectContext:
    """Encapsulates file paths and directory layout for a given project."""

    def __init__(self, name: str | None = None, user: str | None = None, data_root: Path | None = None):
        self._name = name
        self._user = user
        self._data_root = data_root

    @property
    def user(self) -> str:
        return self._user or get_current_user()

    @property
    def data_root(self) -> Path:
        import storage
        return getattr(storage, "DATA_ROOT", self._data_root or DATA_ROOT)

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
    def project_prefix(self) -> str:
        return f"{get_user_prefix(self.user)}{self.name}/"

    @property
    def project_dir(self) -> Path:
        return get_user_root(self.user) / self.name

    def _key(self, filename: str) -> str:
        return f"{self.project_prefix}{filename}"

    @property
    def transactions_key(self) -> str:
        return self._key("transactions.jsonl")

    @property
    def portfolio_key(self) -> str:
        return self._key("portfolio.jsonl")

    @property
    def balance_key(self) -> str:
        return self._key("balance.json")

    @property
    def imports_prefix(self) -> str:
        return f"{self.project_prefix}imports/"

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

    def benchmark_cache_key(self, base_ccy: str) -> str:
        return self._key(f"benchmarks_{base_ccy.upper()}.json")

    def benchmark_cache_path(self, base_ccy: str) -> Path:
        return self.project_dir / f"benchmarks_{base_ccy.upper()}.json"

    def ensure_directories(self) -> None:
        from storage.backends import get_backend
        backend = get_backend()
        backend.mkdir(self.project_prefix)
        backend.mkdir(self.imports_prefix)
