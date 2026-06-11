"""
manual_import.py — Manual transaction file importer

Parses a JSON file containing an array of transactions in Negotium format.
"""
from __future__ import annotations

import json
from pathlib import Path

from transactions import get_all_transactions


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


def _existing_keys() -> set[tuple[str, str, float]]:
    keys: set[tuple[str, str, float]] = set()
    for rec in get_all_transactions():
        for e in rec["entries"]:
            keys.add((rec["date"], e["ticker"].upper(), round(e["amount"], 8)))
    return keys


def import_manual(file_path: str | Path) -> dict:
    valid, msg = validate_manual_file(file_path)
    if not valid:
        return {"success": False, "error": msg}

    transactions = parse_manual_json(file_path)
    existing = _existing_keys()

    imported = 0
    skipped = 0
    for rec in transactions:
        new_entries = [
            e for e in rec["entries"]
            if (rec["date"], e["ticker"].upper(), round(e["amount"], 8)) not in existing
        ]
        if new_entries:
            from transactions import add_transaction
            add_transaction(rec["date"], new_entries)
            imported += 1
        else:
            skipped += 1

    return {"success": True, "imported": imported, "skipped": skipped}
