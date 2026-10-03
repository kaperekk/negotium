"""Application bootstrap helpers for project setup and logging."""

from __future__ import annotations

import logging

import storage


def ensure_project_context() -> tuple[str | None, list[str]]:
    """Initialise the project registry and return current project and project list."""
    storage.init_legacy_project()
    projects = storage.list_projects()

    if not projects:
        if storage.get_current_project() is None:
            storage.create_project("default")
            projects = storage.list_projects()

    current = storage.get_current_project()
    if current is None:
        if projects:
            storage.set_current_project(projects[0])
            current = projects[0]
        else:
            storage.create_project("default")
            current = storage.get_current_project()
            projects = storage.list_projects()

    return current, projects


def configure_import_logging() -> logging.Logger:
    """Attach file-based logging for import-related modules to the active project."""
    _log_dir = storage._project_dir()
    _log_dir.mkdir(parents=True, exist_ok=True)
    _log_file = _log_dir / "import.log"

    logger = logging.getLogger("negotium.imports")
    logger.setLevel(logging.DEBUG)
    if not any(
        isinstance(handler, logging.FileHandler) and handler.baseFilename == str(_log_file.resolve())
        for handler in logger.handlers
    ):
        handler = logging.FileHandler(str(_log_file), encoding="utf-8")
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter("%(asctime)s | %(name)s | %(levelname)s | %(message)s"))
        logger.addHandler(handler)
        logger.propagate = False

        for mod_name in ("xtb_import", "bossa_import", "manual_import"):
            child_logger = logging.getLogger(mod_name)
            child_logger.setLevel(logging.DEBUG)
            if not any(
                isinstance(existing, logging.FileHandler) and existing.baseFilename == str(_log_file.resolve())
                for existing in child_logger.handlers
            ):
                child_logger.addHandler(handler)
                child_logger.propagate = False

    return logger
