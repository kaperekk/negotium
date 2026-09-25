"""
test_importer_classes.py — tests for BaseBrokerImporter implementations and ImportService.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import openpyxl
import pytest

from domain.models import LedgerEntry, Transaction
from services.import_service import ImportService
from services.importers import (
    BaseBrokerImporter,
    BossaImporter,
    ImportResult,
    ManualImporter,
    ValidationResult,
    XtbImporter,
    ingest_transactions,
)


def test_validation_and_import_result_conversions():
    """ValidationResult and ImportResult properly convert to expected types."""
    v = ValidationResult(valid=True, message="OK")
    assert v.to_tuple() == (True, "OK")

    res = ImportResult(success=True, imported=5, skipped=2, error="warn")
    d = res.to_dict()
    assert d == {"success": True, "imported": 5, "skipped": 2, "error": "warn"}

    res_clean = ImportResult(success=True, imported=3, skipped=0)
    assert res_clean.to_dict() == {"success": True, "imported": 3, "skipped": 0}


def test_ingest_transactions_with_transaction_objects(tmp: Path):
    """ingest_transactions handles Transaction models directly."""
    from ledger_core import get_all_transactions

    tx1 = Transaction(
        date="2026-03-01",
        entries=[
            LedgerEntry(ticker="AAPL", amount=10.0),
            LedgerEntry(ticker="USD", amount=-1500.0),
        ],
    )
    tx2 = Transaction(
        date="2026-03-02",
        entries=[
            LedgerEntry(ticker="USD", amount=500.0, account_operation=True),
        ],
    )

    result = ingest_transactions([tx1, tx2])
    assert result.success is True
    assert result.imported == 2
    assert result.skipped == 0

    all_tx = get_all_transactions()
    assert len(all_tx) == 2

    # Ingest again — should deduplicate
    result2 = ingest_transactions([tx1, tx2])
    assert result2.imported == 0
    assert result2.skipped == 2


def test_xtb_importer_class(tmp: Path):
    """XtbImporter class conforms to BaseBrokerImporter interface."""
    importer = XtbImporter()
    assert isinstance(importer, BaseBrokerImporter)

    # Create dummy workbook
    wb = openpyxl.Workbook()
    ws = wb.create_sheet("Cash Operations")
    ws.append(["Type", "Ticker", "Instrument", "Time", "Amount", "ID", "Comment"])
    ws.append(["Deposit", "USD", "", "2026-01-10 10:00:00", 1000.0, 1, ""])
    del wb["Sheet"]
    xlsx_path = tmp / "xtb_test.xlsx"
    wb.save(xlsx_path)
    wb.close()

    val = importer.validate(xlsx_path)
    assert val.valid is True

    parsed = importer.parse(xlsx_path, "USD")
    assert len(parsed) == 1

    res = importer.import_file(xlsx_path, "USD")
    assert res.success is True
    assert res.imported == 1


def test_bossa_importer_class(tmp: Path):
    """BossaImporter class conforms to BaseBrokerImporter interface."""
    importer = BossaImporter()
    assert isinstance(importer, BaseBrokerImporter)

    csv_path = tmp / "bossa_test.csv"
    csv_path.write_text(
        "data;tytuł operacji;szczegóły;kwota;waluta\n"
        "2026-02-01;Przelew do DM BOŚ;;3000.00;PLN\n",
        encoding="utf-8",
    )

    val = importer.validate(csv_path)
    assert val.valid is True

    parsed = importer.parse(csv_path, "PLN")
    assert len(parsed) == 1

    res = importer.import_file(csv_path, "PLN")
    assert res.success is True
    assert res.imported == 1


def test_manual_importer_class(tmp: Path):
    """ManualImporter class conforms to BaseBrokerImporter interface."""
    importer = ManualImporter()
    assert isinstance(importer, BaseBrokerImporter)

    json_path = tmp / "manual_test.json"
    data = [
        {
            "date": "2026-02-15",
            "entries": [
                {"ticker": "PLN", "amount": 2000.0, "account_operation": True}
            ],
        }
    ]
    json_path.write_text(json.dumps(data), encoding="utf-8")

    val = importer.validate(json_path)
    assert val.valid is True

    parsed = importer.parse(json_path)
    assert len(parsed) == 1

    res = importer.import_file(json_path)
    assert res.success is True
    assert res.imported == 1


def test_import_service_orchestration(tmp: Path):
    """ImportService scans directories and calls registered polymorphic importers."""
    from storage.context import ProjectContext

    ctx = ProjectContext(name="test_proj", data_root=tmp)
    ctx.ensure_directories()
    xtb_dir = ctx.imports_dir / "xtb"
    bossa_dir = ctx.imports_dir / "bossa"
    custom_dir = ctx.imports_dir / "custom"
    xtb_dir.mkdir(parents=True, exist_ok=True)
    bossa_dir.mkdir(parents=True, exist_ok=True)
    custom_dir.mkdir(parents=True, exist_ok=True)

    # 1. Custom JSON file
    (custom_dir / "manual.json").write_text(
        json.dumps([{"date": "2026-01-01", "entries": [{"ticker": "USD", "amount": 100}]}]),
        encoding="utf-8",
    )

    # 2. BOSSA CSV file
    (bossa_dir / "PLN_bossa.csv").write_text(
        "data;tytuł operacji;szczegóły;kwota;waluta\n"
        "2026-01-02;Przelew do DM BOŚ;;500;PLN\n",
        encoding="utf-8",
    )

    # 3. XTB Excel file
    wb = openpyxl.Workbook()
    ws = wb.create_sheet("Cash Operations")
    ws.append(["Type", "Ticker", "Instrument", "Time", "Amount", "ID", "Comment"])
    ws.append(["Deposit", "EUR", "", "2026-01-03 10:00:00", 250.0, 1, ""])
    del wb["Sheet"]
    wb.save(xtb_dir / "EUR_xtb.xlsx")
    wb.close()

    service = ImportService(context=ctx)
    file_count, imported_count = service.run_full_refresh(
        today=date(2026, 3, 1),
        base_ccy="PLN",
        detect_currency_fn=lambda name: "EUR" if "EUR" in name else "PLN",
    )

    assert file_count == 3
    assert imported_count == 3
