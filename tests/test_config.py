"""User config — pytest suite."""

from __future__ import annotations

from pathlib import Path


def test_config_defaults(tmp: Path):
    """Config creates default file when missing, loads it correctly."""
    import config
    cfg = config.load()
    assert cfg["default_currency"] == "PLN"
    assert (tmp / "data" / "users" / "test_user" / "config.json").exists(), "config.json should be created"


def test_config_save_and_reload(tmp: Path):
    """Config save → reload round-trip preserves all fields."""
    import config
    custom = {
        "default_currency": "USD",
        "ticker_rules": ["AMZN.DE=AMZ.DE"],
        "isin_tickers": ["IE00B4L5Y983=IWDA.L"],
        "theme": "light",
        "log_scale": True,
    }
    config.save(custom)
    loaded = config.load()
    assert loaded["default_currency"] == "USD"
    assert loaded["isin_tickers"] == ["IE00B4L5Y983=IWDA.L"]
    assert loaded["ticker_rules"] == ["AMZN.DE=AMZ.DE"]
    assert loaded["theme"] == "light"
    assert loaded["log_scale"] is True


def test_config_is_per_user(tmp: Path):
    """Each user has their own config file (no cross-user config sharing)."""
    import storage, config
    from storage.context import set_current_user

    # User 1 (test_user from fixture)
    set_current_user("test_user")
    storage.create_project("proj_a")
    storage.set_current_project("proj_a")
    cfg = config.load()
    cfg["name"] = "User 1 Portfolio"
    config.save(cfg)

    # User 2
    set_current_user("user_2")
    storage.create_project("proj_b")
    storage.set_current_project("proj_b")
    cfg2 = config.load()
    cfg2["name"] = "User 2 Portfolio"
    config.save(cfg2)

    # User 1's config unchanged
    set_current_user("test_user")
    storage.set_current_project("proj_a")
    assert config.load()["name"] == "User 1 Portfolio"

    # User 2's config unchanged
    set_current_user("user_2")
    storage.set_current_project("proj_b")
    assert config.load()["name"] == "User 2 Portfolio"

    # Config files are per-user
    assert (tmp / "data" / "users" / "test_user" / "config.json").exists()
    assert (tmp / "data" / "users" / "user_2" / "config.json").exists()
    # No global config
    assert not (tmp / "data" / "config.json").exists()