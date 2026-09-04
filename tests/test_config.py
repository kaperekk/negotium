"""Global config — pytest suite (split from the original monolithic runner)."""

from __future__ import annotations

from pathlib import Path


def test_config_defaults(tmp: Path):
    """Config creates default file when missing, loads it correctly."""
    import config
    cfg = config.load()
    assert cfg["default_currency"] == "PLN"
    assert (tmp / "data" / "config.json").exists(), "config.json should be created"


def test_config_save_and_reload(tmp: Path):
    """Config save → reload round-trip preserves all fields."""
    import config
    custom = {
        "default_currency": "USD",
        "ticker_rules": ["AMZN.DE=AMZ.DE"],
        "isin_tickers": ["IE00B4L5Y983=IWDA.L"],
        "theme": "light",
    }
    config.save(custom)
    loaded = config.load()
    assert loaded["default_currency"] == "USD"
    assert loaded["isin_tickers"] == ["IE00B4L5Y983=IWDA.L"]
    assert loaded["ticker_rules"] == ["AMZN.DE=AMZ.DE"]
    assert loaded["theme"] == "light"


def test_config_is_global(tmp: Path):
    """All projects share one global config file (no per-project config)."""
    import storage, config

    storage.create_project("proj_a")
    storage.set_current_project("proj_a")
    cfg = config.load()
    cfg["name"] = "Global Portfolio"
    config.save(cfg)

    storage.create_project("proj_b")
    storage.set_current_project("proj_b")
    assert config.load()["name"] == "Global Portfolio"

    # No per-project config files should be created
    assert not (tmp / "data" / "proj_a" / "config.json").exists()
    assert not (tmp / "data" / "proj_b" / "config.json").exists()
    assert (tmp / "data" / "config.json").exists()
