"""
version.py — App version.

Format: v<MAJOR>.<MINOR>.<PATCH>
  - MAJOR.MINOR comes from the VERSION file at the repo root (edit it to bump).
  - PATCH is the number of commits since VERSION was last changed (release
    commits made by scripts/promote.sh are not counted).

scripts/promote.sh computes the version at promotion time and writes it to
RELEASE_VERSION, which the app reads at runtime. If that file is missing, the
version is computed from git directly.

Run `python src/version.py` to print the computed version.
"""
from __future__ import annotations

import subprocess
from functools import lru_cache
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_VERSION_FILE = _ROOT / "VERSION"
RELEASE_FILE = _ROOT / "RELEASE_VERSION"
RELEASE_COMMIT_PREFIX = "release: "


def _git(*args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", *args], cwd=_ROOT, capture_output=True, text=True, timeout=5, check=True
        )
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def compute_version() -> str:
    """Compute e.g. 'v1.1.3' from git. Falls back to 'v1.1' when git is unavailable."""
    try:
        base = _VERSION_FILE.read_text().strip()
    except OSError:
        base = "0.0"

    # Count commits after the one that last touched VERSION, ignoring release commits.
    bump = _git("log", "-1", "--format=%H", "--", "VERSION")
    rev_range = f"{bump}..HEAD" if bump else "HEAD"
    patch = _git(
        "rev-list", "--count", "--invert-grep", f"--grep=^{RELEASE_COMMIT_PREFIX}", rev_range
    )
    return f"v{base}.{patch}" if patch is not None else f"v{base}"


@lru_cache(maxsize=1)
def get_version() -> str:
    """Return the released version from RELEASE_VERSION, or compute it from git."""
    try:
        released = RELEASE_FILE.read_text().strip()
        if released:
            return released
    except OSError:
        pass
    return compute_version()


if __name__ == "__main__":
    print(compute_version())
