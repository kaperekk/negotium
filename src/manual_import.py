"""
manual_import.py — Structured manual JSON transaction importer

Parses JSON statements and converts them into Negotium Transaction domain models.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from domain.models import LedgerEntry, Transaction
from services.importers.base import ingest_transactions

log = logging.getLogger(__name__)


def validate_manual_file(file_path: str | Path) -> tuple[bool, str]:
    """Validate JSON file formatting and schema requirements."""
    try:
        text = Path(file_path).read_text(encoding="utf-8").strip()
        if not text:
            return False, "File is empty."
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON: {e}"
    except Exception as e:
        return False, f"Cannot read file: {e}"

    if not isinstance(data, list):
        return False, "File must contain a JSON array of transactions."

    for i, tx in enumerate(data):
        if not isinstance(tx, dict):
            return False, f"Transaction {i} is not an object."
        if "date" not in tx:
            return False, f"Transaction {i} missing 'date'."
        if "entries" not in tx or not isinstance(tx["entries"], list):
            return False, f"Transaction {i} missing 'entries' array."
        for j, e in enumerate(tx["entries"]):
            if "ticker" not in e:
                return False, f"Transaction {i}, entry {j} missing 'ticker'."
            if "amount" not in e:
                return False, f"Transaction {i}, entry {j} missing 'amount'."

    return True, "Valid manual transaction file."


def parse_manual_json(file_path: str | Path) -> list[dict]:
    """Parse manual JSON file into list of transaction dicts using domain models."""
    data = json.loads(Path(file_path).read_text(encoding="utf-8"))
    transactions = [Transaction.from_dict(tx) for tx in data]
    return [tx.to_dict() for tx in transactions]


def import_manual(file_path: str | Path) -> dict[str, Any]:
    """Validate, parse, deduplicate, and ingest manual JSON transactions into the active ledger."""
    log.info("=== Manual import: %s ===", file_path)
    valid, msg = validate_manual_file(file_path)
    if not valid:
        log.error("Validation failed: %s", msg)
        return {"success": False, "error": msg}

    transactions = parse_manual_json(file_path)
    result = ingest_transactions(transactions)
    return result.to_dict()
