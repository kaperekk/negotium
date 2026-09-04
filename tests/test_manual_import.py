"""Manual JSON importer — pytest suite (split from the original monolithic runner)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
import json


def test_manual_validate_errors(tmp: Path):
    """validate_manual_file catches various malformed inputs."""
    from manual_import import validate_manual_file

    empty = tmp / "empty.json"
    empty.write_text("")
    valid, msg = validate_manual_file(empty)
    assert not valid
    assert "empty" in msg.lower()

    bad_json = tmp / "bad.json"
    bad_json.write_text("{not json}")
    valid, msg = validate_manual_file(bad_json)
    assert not valid

    not_array = tmp / "not_array.json"
    not_array.write_text('{"date": "2023-01-03"}')
    valid, msg = validate_manual_file(not_array)
    assert not valid
    assert "array" in msg.lower()

    missing_date = tmp / "missing_date.json"
    missing_date.write_text('[{"entries": [{"ticker": "AAPL", "amount": 10}]}]')
    valid, msg = validate_manual_file(missing_date)
    assert not valid
    assert "date" in msg.lower()

    missing_ticker = tmp / "missing_ticker.json"
    missing_ticker.write_text('[{"date": "2023-01-03", "entries": [{"amount": 10}]}]')
    valid, msg = validate_manual_file(missing_ticker)
    assert not valid
    assert "ticker" in msg.lower()


def test_manual_parse_and_import(tmp: Path):
    """parse_manual_json parses correctly; import_manual deduplicates."""
    from manual_import import parse_manual_json, import_manual

    data = [
        {
            "date": "2023-01-03",
            "entries": [
                {"ticker": "AAPL", "amount": 10.0},
                {"ticker": "USD", "amount": -1250.0},
            ],
        },
        {
            "date": "2023-01-04",
            "entries": [
                {"ticker": "MSFT", "amount": 5.0, "account_operation": True},
            ],
        },
    ]

    json_file = tmp / "test_manual.json"
    json_file.write_text(json.dumps(data))

    parsed = parse_manual_json(json_file)
    assert len(parsed) == 2
    assert parsed[0]["date"] == "2023-01-03"
    assert len(parsed[0]["entries"]) == 2
    assert parsed[1]["entries"][0].get("account_operation") is True

    result = import_manual(json_file)
    assert result["success"] is True
    assert result["imported"] == 2

    # Import again — should skip duplicates
    result2 = import_manual(json_file)
    assert result2["success"] is True
    assert result2["skipped"] == 2
    assert result2["imported"] == 0
