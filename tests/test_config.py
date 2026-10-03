"""Config — pytest suite."""

from __future__ import annotations

from pathlib import Path


def test_config_defaults(tmp: Path):
    """Config loads defaults from committed file."""
    import config
    cfg = config.load()
    assert cfg["default_currency"] == "PLN"
    assert "ticker_rules" in cfg
    assert "isin_tickers" in cfg


def test_config_save_and_reload(tmp: Path):
    """Config save → reload round-trip preserves all fields (user config)."""
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


def test_config_per_user_isolation(tmp: Path):
    """Each user has their own config in storage."""
    import storage, config

    # User 1
    storage.create_user("user1")
    storage.set_current_user("user1")
    cfg1 = config.load()
    cfg1["default_currency"] = "USD"
    cfg1["theme"] = "light"
    config.save(cfg1)

    # User 2
    storage.create_user("user2")
    storage.set_current_user("user2")
    cfg2 = config.load()
    assert cfg2["default_currency"] == "PLN"  # global default
    assert cfg2["theme"] == "dark"  # global default

    # User 1 config unchanged
    storage.set_current_user("user1")
    cfg1_reloaded = config.load()
    assert cfg1_reloaded["default_currency"] == "USD"
    assert cfg1_reloaded["theme"] == "light"