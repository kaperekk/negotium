"""
manual_import.py — Manual transaction file importer

Parses a JSON file containing an array of transactions in Negotium format.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from ledger_core import get_all_transactions

log = logging.getLogger(__name__)


def validate_manual_file(file_path: str | Path) -> tuple[bool, str]:
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
    data = json.loads(Path(file_path).read_text(encoding="utf-8"))
    transactions = []
    for tx in data:
        entries = []
        for e in tx["entries"]:
            entry = {"ticker": e["ticker"], "amount": float(e["amount"])}
            if e.get("account_operation"):
                entry["account_operation"] = True
            entries.append(entry)
        transactions.append({"date": tx["date"], "entries": entries})
    return transactions


def _existing_entry_counts() -> dict[tuple[str, str, float], int]:
    from ledger_core import existing_entry_counts
    return existing_entry_counts()


def import_manual(file_path: str | Path) -> dict:
    log.info("=== Manual import: %s ===", file_path)
    valid, msg = validate_manual_file(file_path)
    if not valid:
        log.error("Validation failed: %s", msg)
        return {"success": False, "error": msg}

    transactions = parse_manual_json(file_path)
    existing = _existing_entry_counts()

    imported = 0
    skipped = 0
    for rec in transactions:
        new_entries = []
        for e in rec["entries"]:
            key = (rec["date"], e["ticker"].upper(), round(float(e["amount"]), 8))
            if existing.get(key, 0) > 0:
                existing[key] -= 1
            else:
                new_entries.append(e)
        if new_entries:
            from ledger_core import add_transaction
            add_transaction(rec["date"], new_entries)
            imported += 1
        else:
            skipped += 1

    log.info("Result: %d imported, %d skipped (duplicates)", imported, skipped)
    return {"success": True, "imported": imported, "skipped": skipped}
