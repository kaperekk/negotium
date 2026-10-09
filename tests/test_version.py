"""Tests for app version (RELEASE_VERSION file and git-derived fallback)."""
import re
import subprocess

import version
from version import compute_version, get_version


def test_version_format():
    get_version.cache_clear()
    assert re.fullmatch(r"v\d+\.\d+(\.\d+)?", get_version())


def test_release_file_takes_precedence(tmp_path, monkeypatch):
    release = tmp_path / "RELEASE_VERSION"
    release.write_text("v9.9.9\n")
    monkeypatch.setattr(version, "RELEASE_FILE", release)
    get_version.cache_clear()
    try:
        assert get_version() == "v9.9.9"
    finally:
        get_version.cache_clear()


def test_release_commits_not_counted(tmp_path, monkeypatch):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    (tmp_path / "VERSION").write_text("2.3\n")
    git("add", "VERSION")
    git("commit", "-qm", "bump")
    monkeypatch.setattr(version, "_ROOT", tmp_path)
    monkeypatch.setattr(version, "_VERSION_FILE", tmp_path / "VERSION")

    assert compute_version() == "v2.3.0"
    git("commit", "-q", "--allow-empty", "-m", "feature")
    git("commit", "-q", "--allow-empty", "-m", "release: v2.3.1")
    assert compute_version() == "v2.3.1"
    git("commit", "-q", "--allow-empty", "-m", "another")
    assert compute_version() == "v2.3.2"
