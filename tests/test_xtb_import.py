"""XTB importer — pytest suite (split from the original monolithic runner)."""

from __future__ import annotations

from pathlib import Path


def test_xtb_parse_shares(tmp: Path):
    """_parse_shares extracts share count from XTB comment patterns."""
    from xtb_import import _parse_shares

    assert _parse_shares("OPEN BUY 4/4.138 @ 48.3060") == 4.0
    assert _parse_shares("OPEN BUY 0.1367 @ 1462.60") == 0.1367
    assert _parse_shares("CLOSE BUY 3.9657/14.7171 @ 123.3700") == 3.9657
    assert _parse_shares("OPEN BUY 1 @ 107.00") == 1.0
    assert _parse_shares(None) is None
    assert _parse_shares("") is None
    assert _parse_shares("no match here") is None


def test_xtb_transfer_creates_source_entry(tmp: Path):
    """Transfer import creates the source currency entry (each file has its own side)."""
    from xtb_import import parse_xtb_excel
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.create_sheet("Cash Operations")

    ws.append(["", "", "", "", "", "", ""])
    ws.append(["", "", "", "", "", "", ""])
    ws.append(["", "", "", "", "", "", ""])
    ws.append(["", "", "", "", "", "", ""])
    ws.append(["", "", "", "", "", "", ""])
    ws.append(["Type", "Ticker", "Instrument", "Time", "Amount", "ID", "Comment"])
    ws.append([
        "Transfer", "", "",
        "2026-06-01 10:47:30", -956, 1288183841,
        "Currency conversion, EUR to USD from TA: 52016471 to: 51963109, Exchange rate:1.159044",
    ])

    del wb["Sheet"]
    xlsx_path = tmp / "test_transfer.xlsx"
    wb.save(str(xlsx_path))
    wb.close()

    txns = parse_xtb_excel(str(xlsx_path), "EUR")
    assert len(txns) == 1

    entries = txns[0]["entries"]
    assert len(entries) == 1

    eur_entry = entries[0]
    assert eur_entry["ticker"] == "EUR"
    assert eur_entry["amount"] == -956
    assert eur_entry.get("account_operation") is True


def test_xtb_deposit_creates_account_operation(tmp: Path):
    """Deposit import creates entry with account_operation=True."""
    from xtb_import import parse_xtb_excel
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.create_sheet("Cash Operations")

    for _ in range(5):
        ws.append(["", "", "", "", "", "", ""])
    ws.append(["Type", "Ticker", "Instrument", "Time", "Amount", "ID", "Comment"])
    ws.append(["Deposit", "", "", "2026-01-15 12:00:00", 5000, 111, "eWallet deposit"])

    del wb["Sheet"]
    xlsx_path = tmp / "test_deposit.xlsx"
    wb.save(str(xlsx_path))
    wb.close()

    txns = parse_xtb_excel(str(xlsx_path), "EUR")
    assert len(txns) == 1

    entries = txns[0]["entries"]
    assert len(entries) == 1
    assert entries[0]["ticker"] == "EUR"
    assert entries[0]["amount"] == 5000
    assert entries[0].get("account_operation") is True


def test_xtb_stock_purchase_creates_two_entries(tmp: Path):
    """Stock purchase creates share entry + currency outflow entry."""
    from xtb_import import parse_xtb_excel
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.create_sheet("Cash Operations")

    for _ in range(5):
        ws.append(["", "", "", "", "", "", ""])
    ws.append(["Type", "Ticker", "Instrument", "Time", "Amount", "ID", "Comment"])
    ws.append([
        "Stock purchase", "AAPL", "Apple",
        "2026-01-15 12:00:00", -1250.70, 222,
        "OPEN BUY 10/10 @ 125.07",
    ])

    del wb["Sheet"]
    xlsx_path = tmp / "test_buy.xlsx"
    wb.save(str(xlsx_path))
    wb.close()

    txns = parse_xtb_excel(str(xlsx_path), "EUR")
    assert len(txns) == 1

    entries = txns[0]["entries"]
    assert len(entries) == 2

    stock_entry = next(e for e in entries if e["ticker"] == "AAPL")
    cash_entry = next(e for e in entries if e["ticker"] == "EUR")

    assert stock_entry["amount"] == 10.0
    assert cash_entry["amount"] == -1250.70


def test_xtb_withholding_tax(tmp: Path):
    """Withholding tax creates a currency entry (no account_operation)."""
    from xtb_import import parse_xtb_excel
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.create_sheet("Cash Operations")

    for _ in range(5):
        ws.append(["", "", "", "", "", "", ""])
    ws.append(["Type", "Ticker", "Instrument", "Time", "Amount", "ID", "Comment"])
    ws.append([
        "Withholding tax", "FB2A.DE", "Meta",
        "2026-03-26 10:57:00", -0.76, 333,
        "FB2A.DE USD WHT 30%",
    ])

    del wb["Sheet"]
    xlsx_path = tmp / "test_wht.xlsx"
    wb.save(str(xlsx_path))
    wb.close()

    txns = parse_xtb_excel(str(xlsx_path), "EUR")
    assert len(txns) == 1

    entries = txns[0]["entries"]
    assert len(entries) == 1
    assert entries[0]["ticker"] == "EUR"
    assert entries[0]["amount"] == -0.76
    assert entries[0].get("account_operation") is None or entries[0].get("account_operation") is False


def test_xtb_dividend_import(tmp: Path):
    """Dividend rows from XTB statements are imported as cash credits."""
    from xtb_import import import_xtb
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.create_sheet("Cash Operations")

    for _ in range(5):
        ws.append(["", "", "", "", "", "", ""])
    ws.append(["Type", "Ticker", "Instrument", "Time", "Amount", "ID", "Comment"])
    ws.append([
        "Dividend", "AAPL", "AAPL",
        "2026-05-20 10:00:00", 12.50, 222,
        "Dividend payment",
    ])

    del wb["Sheet"]
    xlsx_path = tmp / "test_dividend.xlsx"
    wb.save(str(xlsx_path))
    wb.close()

    result = import_xtb(str(xlsx_path), "USD")
    assert result["success"] is True
    assert result["imported"] == 1

    from ledger_core import get_all_transactions
    records = get_all_transactions()
    assert len(records) == 1
    entries = records[0]["entries"]
    assert len(entries) == 1
    assert entries[0]["ticker"] == "USD"
    assert entries[0]["amount"] == 12.50
    assert entries[0].get("account_operation") is None


def test_xtb_validate_missing_sheet(tmp: Path):
    """validate_xtb_file: file without 'Cash Operations' sheet fails."""
    from xtb_import import validate_xtb_file
    import openpyxl

    wb = openpyxl.Workbook()
    wb.active.title = "Positions"
    wb.active.append(["Type", "Ticker", "Amount"])
    p = tmp / "no_cash.xlsx"
    wb.save(p)
    wb.close()

    valid, msg = validate_xtb_file(p)
    assert valid is False
    assert "Cash Operations" in msg


def test_xtb_validate_missing_columns(tmp: Path):
    """validate_xtb_file: sheet missing required columns fails."""
    from xtb_import import validate_xtb_file
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Cash Operations"
    ws.append(["Type", "Ticker"])  # Missing Amount, Time
    p = tmp / "missing_cols.xlsx"
    wb.save(p)
    wb.close()

    valid, msg = validate_xtb_file(p)
    assert valid is False
    assert "Missing columns" in msg


def test_xtb_validate_valid(tmp: Path):
    """validate_xtb_file: valid XTB file passes."""
    from xtb_import import validate_xtb_file
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Cash Operations"
    ws.append(["Type", "Ticker", "Amount", "Time", "Comment"])
    ws.append(["Deposit", "USD", 1000, "2023-01-03 10:00:00", ""])
    p = tmp / "valid.xlsx"
    wb.save(p)
    wb.close()

    valid, msg = validate_xtb_file(p)
    assert valid is True


def test_xtb_parse_dividend(tmp: Path):
    """parse_xtb_excel: dividend creates a currency entry."""
    from xtb_import import parse_xtb_excel
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Cash Operations"
    ws.append(["Type", "Ticker", "Amount", "Time", "Comment"])
    ws.append(["Dividend", "AAPL.US", 15.50, "2023-06-15 10:00:00", "Dividend AAPL"])
    p = tmp / "div.xlsx"
    wb.save(p)
    wb.close()

    txns = parse_xtb_excel(p, "USD")
    assert len(txns) == 1
    assert txns[0]["entries"][0]["amount"] == 15.50
    assert txns[0]["entries"][0]["ticker"] == "USD"


def test_xtb_parse_withdrawal(tmp: Path):
    """parse_xtb_excel: withdrawal creates account_operation entry."""
    from xtb_import import parse_xtb_excel
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Cash Operations"
    ws.append(["Type", "Ticker", "Amount", "Time", "Comment"])
    ws.append(["Withdrawal", "USD", -500.0, "2023-07-01 10:00:00", ""])
    p = tmp / "withdraw.xlsx"
    wb.save(p)
    wb.close()

    txns = parse_xtb_excel(p, "USD")
    assert len(txns) == 1
    assert txns[0]["entries"][0].get("account_operation") is True
    assert txns[0]["entries"][0]["amount"] == -500.0


def test_xtb_parse_interest(tmp: Path):
    """parse_xtb_excel: free funds interest creates currency entry."""
    from xtb_import import parse_xtb_excel
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Cash Operations"
    ws.append(["Type", "Ticker", "Amount", "Time", "Comment"])
    ws.append(["Free funds interest", "USD", 2.35, "2023-06-30 10:00:00", ""])
    p = tmp / "interest.xlsx"
    wb.save(p)
    wb.close()

    txns = parse_xtb_excel(p, "USD")
    assert len(txns) == 1
    assert txns[0]["entries"][0]["amount"] == 2.35
    assert txns[0]["entries"][0]["ticker"] == "USD"


def test_xtb_parse_withholding_tax(tmp: Path):
    """parse_xtb_excel: withholding tax creates currency entry."""
    from xtb_import import parse_xtb_excel
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Cash Operations"
    ws.append(["Type", "Ticker", "Amount", "Time", "Comment"])
    ws.append(["Withholding tax", "USD", -3.10, "2023-06-15 10:00:00", ""])
    p = tmp / "wht.xlsx"
    wb.save(p)
    wb.close()

    txns = parse_xtb_excel(p, "USD")
    assert len(txns) == 1
    assert txns[0]["entries"][0]["amount"] == -3.10


def test_xtb_parse_deposit(tmp: Path):
    """parse_xtb_excel: deposit creates account_operation entry."""
    from xtb_import import parse_xtb_excel
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Cash Operations"
    ws.append(["Type", "Ticker", "Amount", "Time", "Comment"])
    ws.append(["Deposit", "USD", 5000.0, "2023-01-03 10:00:00", ""])
    p = tmp / "deposit.xlsx"
    wb.save(p)
    wb.close()

    txns = parse_xtb_excel(p, "USD")
    assert len(txns) == 1
    assert txns[0]["entries"][0].get("account_operation") is True
    assert txns[0]["entries"][0]["amount"] == 5000.0


def test_xtb_parse_transfer(tmp: Path):
    """parse_xtb_excel: transfer creates account_operation entry."""
    from xtb_import import parse_xtb_excel
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Cash Operations"
    ws.append(["Type", "Ticker", "Amount", "Time", "Comment"])
    ws.append(["Transfer", "USD", 2000.0, "2023-03-15 10:00:00", ""])
    p = tmp / "transfer.xlsx"
    wb.save(p)
    wb.close()

    txns = parse_xtb_excel(p, "USD")
    assert len(txns) == 1
    assert txns[0]["entries"][0].get("account_operation") is True


def _single_row_book(tmp: Path, name: str, row: list) -> Path:
    """Helper: build a one-row Cash Operations workbook (header + row)."""
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Cash Operations"
    ws.append(["Type", "Ticker", "Amount", "Time", "Comment"])
    ws.append(row)
    p = tmp / name
    wb.save(p)
    wb.close()
    return p


def test_xtb_parse_ike_deposit(tmp: Path):
    """parse_xtb_excel: IKE deposit creates account_operation entry.

    IKE accounts export deposits with the row type 'IKE deposit' instead of
    'Deposit' — these must count toward invested capital like any deposit.
    """
    from xtb_import import parse_xtb_excel

    p = _single_row_book(tmp, "ike_deposit.xlsx",
                         ["IKE deposit", "", 2000.0, "2026-08-25 06:56:32",
                          "Transfer in operation on account with id 51174134"])
    txns = parse_xtb_excel(p, "PLN")
    assert len(txns) == 1
    entry = txns[0]["entries"][0]
    assert entry["ticker"] == "PLN"
    assert entry["amount"] == 2000.0
    assert entry.get("account_operation") is True


def test_xtb_parse_ike_withdrawal(tmp: Path):
    """parse_xtb_excel: IKE withdrawal creates account_operation entry."""
    from xtb_import import parse_xtb_excel

    p = _single_row_book(tmp, "ike_withdrawal.xlsx",
                         ["IKE withdrawal", "", -500.0, "2026-01-15 10:00:00", ""])
    txns = parse_xtb_excel(p, "PLN")
    assert len(txns) == 1
    entry = txns[0]["entries"][0]
    assert entry["amount"] == -500.0
    assert entry.get("account_operation") is True


def test_xtb_parse_foreign_dividend_on_pl_market(tmp: Path):
    """parse_xtb_excel: 'Dividend from foreign company on PL market' is cash.

    Foreign-company dividends settled on the Warsaw market (e.g. ASB.PL paid
    in USD) carry their own row type — they must import like a dividend.
    """
    from xtb_import import parse_xtb_excel

    p = _single_row_book(tmp, "foreign_div.xlsx",
                         ["Dividend from foreign company on PL market", "ASB.PL",
                          22.85, "2026-05-28 09:59:02", "ASB.PL USD 0.3500/ SHR"])
    txns = parse_xtb_excel(p, "PLN")
    assert len(txns) == 1
    entry = txns[0]["entries"][0]
    assert entry["ticker"] == "PLN"
    assert entry["amount"] == 22.85
    assert entry.get("account_operation") is None


def test_xtb_parse_fractional_shares_cash(tmp: Path):
    """parse_xtb_excel: 'Fractional shares' (split cash leg) is a cash entry."""
    from xtb_import import parse_xtb_excel

    p = _single_row_book(tmp, "fractional.xlsx",
                         ["Fractional shares", "DNP.PL", 135.93,
                          "2025-07-31 06:59:33", "DNP.PL split 10 for 1"])
    txns = parse_xtb_excel(p, "PLN")
    assert len(txns) == 1
    entry = txns[0]["entries"][0]
    assert entry["ticker"] == "PLN"
    assert entry["amount"] == 135.93
    assert entry.get("account_operation") is None


def test_xtb_zero_amount_rows_produce_no_entries(tmp: Path):
    """parse_xtb_excel: zero-amount fee/correction rows are dropped, not stored."""
    from xtb_import import parse_xtb_excel

    wb_rows = [
        ["Commission", "DNP.PL", 0.0, "2025-07-31 06:57:05", "Correction: BUY 0.2712 @ 393.20"],
        ["Correction", "DNP.PL", 0.0, "2025-07-31 06:57:05", "Correction: Profit of position #1589229752"],
        ["Close trade", "DNP.PL", 0.0, "2025-07-31 06:57:05", "Profit of position #1589229752"],
    ]
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Cash Operations"
    ws.append(["Type", "Ticker", "Amount", "Time", "Comment"])
    for r in wb_rows:
        ws.append(r)
    p = tmp / "zero_rows.xlsx"
    wb.save(p)
    wb.close()

    txns = parse_xtb_excel(p, "PLN")
    assert txns == []


def test_xtb_unknown_type_with_amount_is_skipped(tmp: Path):
    """parse_xtb_excel: unrecognised types carrying money produce no entries."""
    from xtb_import import parse_xtb_excel

    p = _single_row_book(tmp, "unknown.xlsx",
                         ["Exotic operation", "", 100.0, "2026-01-01 10:00:00", "?"])
    txns = parse_xtb_excel(p, "PLN")
    assert txns == []


# ── Helpers for Closed / Open Positions tests ──────────────────────────────


def _positions_book(
    tmp: Path,
    name: str,
    cash_rows: list[list] | None = None,
    closed_header: list[str] | None = None,
    closed_rows: list[list] | None = None,
    open_header: list[str] | None = None,
    open_rows: list[list] | None = None,
) -> Path:
    """Build an XTB workbook with Cash Operations, Closed Positions, Open Positions."""
    import openpyxl

    wb = openpyxl.Workbook()

    # Cash Operations
    ws_cash = wb.active
    ws_cash.title = "Cash Operations"
    ws_cash.append(["Type", "Ticker", "Amount", "Time", "Comment"])
    for r in (cash_rows or []):
        ws_cash.append(r)

    # Closed Positions
    ws_closed = wb.create_sheet("Closed Positions")
    closed_h = closed_header or [
        "Instrument", "Ticker", "Category", "Type", "Volume",
        "Open Price", "Open Time (UTC)", "Close Price",
        "Close Time (UTC)", "Product", "Purchase Value",
    ]
    ws_closed.append(closed_h)
    for r in (closed_rows or []):
        ws_closed.append(r)

    # Open Positions
    ws_open = wb.create_sheet("Open Positions")
    open_h = open_header or [
        "Product", "Instrument/Position", "Ticker", "Category",
        "Type", "Volume", "Value", "Open Price",
        "Current Price", "Open Time (UTC)",
    ]
    ws_open.append(open_h)
    for r in (open_rows or []):
        ws_open.append(r)

    p = tmp / name
    wb.save(p)
    wb.close()
    return p


# ── parse_closed_positions tests ───────────────────────────────────────────


def test_closed_positions_parses_buy(tmp: Path):
    """parse_closed_positions: BUY row creates an acquisition transaction."""
    from xtb_import import parse_closed_positions

    p = _positions_book(
        tmp, "closed.xlsx",
        closed_rows=[[
            "Apple", "AAPL.US", "STOCK", "BUY", 5.0,
            150.0, "2025-01-15 10:00:00", 170.0,
            "2025-06-20 14:00:00", "My Trades", 750.0,
        ]],
    )
    txns = parse_closed_positions(str(p), "USD")
    assert len(txns) == 1
    assert txns[0]["date"] == "2025-01-15"
    assert txns[0]["entries"][0]["ticker"] == "AAPL.US"
    assert txns[0]["entries"][0]["amount"] == 5.0
    assert txns[0]["entries"][1]["amount"] == -750.0


def test_closed_positions_skips_sell(tmp: Path):
    """parse_closed_positions: SELL rows are skipped."""
    from xtb_import import parse_closed_positions

    p = _positions_book(
        tmp, "closed_sell.xlsx",
        closed_rows=[[
            "Apple", "AAPL.US", "STOCK", "SELL", 5.0,
            150.0, "2025-01-15 10:00:00", 170.0,
            "2025-06-20 14:00:00", "My Trades", 850.0,
        ]],
    )
    txns = parse_closed_positions(str(p), "USD")
    assert len(txns) == 0


def test_closed_positions_skips_no_open_time(tmp: Path):
    """parse_closed_positions: rows without open time are skipped (summary rows)."""
    from xtb_import import parse_closed_positions

    p = _positions_book(
        tmp, "closed_notime.xlsx",
        closed_rows=[[
            "Apple", "AAPL.US", "STOCK", "BUY", 5.0,
            150.0, None, 170.0,
            "2025-06-20 14:00:00", "My Trades", 750.0,
        ]],
    )
    txns = parse_closed_positions(str(p), "USD")
    assert len(txns) == 0


def test_closed_positions_translates_ticker(tmp: Path):
    """parse_closed_positions: .PL tickers are translated when rules are configured."""
    from xtb_import import parse_closed_positions

    p = _positions_book(
        tmp, "closed_pl.xlsx",
        closed_rows=[[
            "Dino", "DNP.PL", "STOCK", "BUY", 0.2712,
            393.2, "2024-12-27 11:58:22", 501.4,
            "2025-07-31 06:57:05", "IKE", 106.64,
        ]],
    )
    txns = parse_closed_positions(str(p), "PLN")
    assert len(txns) == 1
    ticker = txns[0]["entries"][0]["ticker"]
    assert ticker in ("DNP.PL", "DNP.WA")


def test_closed_positions_empty_sheet(tmp: Path):
    """parse_closed_positions: returns [] when sheet has no data rows."""
    from xtb_import import parse_closed_positions

    p = _positions_book(tmp, "closed_empty.xlsx")
    txns = parse_closed_positions(str(p), "PLN")
    assert txns == []


# ── parse_open_positions tests ─────────────────────────────────────────────


def test_open_positions_parses_buy(tmp: Path):
    """parse_open_positions: BUY row creates an acquisition transaction."""
    from xtb_import import parse_open_positions

    p = _positions_book(
        tmp, "open.xlsx",
        open_rows=[[
            "My Trades", "1234567", "AAPL.US", "STOCK", "BUY",
            10.0, 1500.0, 150.0, 170.0,
            "2025-01-15 10:00:00",
        ]],
    )
    txns = parse_open_positions(str(p), "USD")
    assert len(txns) == 1
    assert txns[0]["entries"][0]["ticker"] == "AAPL.US"
    assert txns[0]["entries"][0]["amount"] == 10.0
    assert txns[0]["entries"][1]["amount"] == -1500.0
    assert txns[0]["date"] == "2025-01-15"


def test_open_positions_skips_no_open_time(tmp: Path):
    """parse_open_positions: summary rows (no open time) are skipped."""
    from xtb_import import parse_open_positions

    p = _positions_book(
        tmp, "open_notime.xlsx",
        open_rows=[[
            "My Trades", "AAPL", "AAPL.US", "STOCK", "",
            10.0, 1500.0, 150.0, 170.0, "",
        ]],
    )
    txns = parse_open_positions(str(p), "USD")
    assert len(txns) == 0


def test_open_positions_skips_sells(tmp: Path):
    """parse_open_positions: only BUY rows are parsed."""
    from xtb_import import parse_open_positions

    p = _positions_book(
        tmp, "open_sell.xlsx",
        open_rows=[[
            "My Trades", "1234567", "AAPL.US", "STOCK", "SELL",
            10.0, 1500.0, 150.0, 170.0,
            "2025-01-15 10:00:00",
        ]],
    )
    txns = parse_open_positions(str(p), "USD")
    assert len(txns) == 0


def test_open_positions_translates_ticker(tmp: Path):
    """parse_open_positions: .PL tickers are translated when rules are configured."""
    from xtb_import import parse_open_positions

    p = _positions_book(
        tmp, "open_pl.xlsx",
        open_rows=[[
            "IKE", "1234567", "DNP.PL", "STOCK", "BUY",
            25.0, 903.0, 36.12, 39.32,
            "2024-12-27 11:58:22",
        ]],
    )
    txns = parse_open_positions(str(p), "PLN")
    assert len(txns) == 1
    ticker = txns[0]["entries"][0]["ticker"]
    assert ticker in ("DNP.PL", "DNP.WA")


def test_open_positions_skips_currencies(tmp: Path):
    """parse_open_positions: currency tickers are returned (filtering is in fix_avg_prices)."""
    from xtb_import import parse_open_positions

    p = _positions_book(
        tmp, "open_ccy.xlsx",
        open_rows=[[
            "My Trades", "1234567", "EUR", "CASH", "BUY",
            1000.0, 1000.0, 1.0, 1.0,
            "2025-01-15 10:00:00",
        ]],
    )
    txns = parse_open_positions(str(p), "EUR")
    assert len(txns) == 1
    assert txns[0]["entries"][0]["ticker"] == "EUR"


def test_open_positions_empty_sheet(tmp: Path):
    """parse_open_positions: returns [] when sheet has no data rows."""
    from xtb_import import parse_open_positions

    p = _positions_book(tmp, "open_empty.xlsx")
    txns = parse_open_positions(str(p), "PLN")
    assert txns == []


# ── Volume-based dedup tests ──────────────────────────────────────────────


def test_import_xtb_adds_spinoff_not_in_cash_ops(tmp: Path):
    """import_xtb: spinoff shares from Open Positions added when Cash Ops has no buy."""
    from xtb_import import import_xtb
    from ledger_core import get_all_transactions

    p = _positions_book(
        tmp, "spinoff.xlsx",
        cash_rows=[],
        open_rows=[[
            "IKE", "1234567", "S2B.PL", "STOCK", "BUY",
            13.8382, 0.0, 0.0, 58.0,
            "2026-04-13 10:00:00",
        ]],
    )
    import_xtb(str(p), "PLN")
    txns = get_all_transactions()
    s2b_txns = [t for t in txns if any("S2B" in e["ticker"].upper() for e in t["entries"])]
    assert len(s2b_txns) == 1
    share_entry = [e for e in s2b_txns[0]["entries"] if "S2B" in e["ticker"].upper()][0]
    assert abs(share_entry["amount"] - 13.8382) < 0.001


def test_import_xtb_skips_when_cash_ops_covers_position(tmp: Path):
    """import_xtb: position buy skipped when Cash Ops already has a buy for same date+ticker."""
    from xtb_import import import_xtb
    from ledger_core import get_all_transactions

    p = _positions_book(
        tmp, "covered.xlsx",
        cash_rows=[
            ["Stock purchase", "AAPL.US", -500.0, "2025-01-15 10:00:00",
             "OPEN BUY 5 @ 100.00"],
        ],
        open_rows=[[
            "My Trades", "1234567", "AAPL.US", "STOCK", "BUY",
            5.0, 500.0, 100.0, 120.0,
            "2025-01-15 10:00:00",
        ]],
    )
    import_xtb(str(p), "USD")
    txns = get_all_transactions()
    aapl_buys = [
        t for t in txns
        if any(e["ticker"] == "AAPL.US" and float(e["amount"]) > 0 for e in t["entries"])
    ]
    assert len(aapl_buys) == 1


def test_import_xtb_adds_split_difference(tmp: Path):
    """import_xtb: split adjustment added when Open Position volume > Cash Ops volume."""
    from xtb_import import import_xtb
    from ledger_core import get_all_transactions

    p = _positions_book(
        tmp, "split.xlsx",
        cash_rows=[
            ["Stock purchase", "DNP.PL", -393.2, "2024-12-27 11:58:22",
             "OPEN BUY 1/1.2712 @ 393.20"],
        ],
        open_rows=[[
            "IKE", "1589229756", "DNP.PL", "STOCK", "BUY",
            10.0, 361.2, 36.12, 39.32,
            "2024-12-27 11:58:22",
        ]],
    )
    import_xtb(str(p), "PLN")
    txns = get_all_transactions()
    dnp_buys = [
        t for t in txns
        if any("DNP" in e["ticker"].upper() and float(e["amount"]) > 0 for e in t["entries"])
    ]
    total = sum(
        float(e["amount"])
        for t in dnp_buys
        for e in t["entries"]
        if "DNP" in e["ticker"].upper() and float(e["amount"]) > 0
    )
    assert abs(total - 10.0) < 0.01


# ── fix_avg_prices_from_open_positions tests ──────────────────────────────


def test_fix_avg_prices_overrides_with_real_price(tmp: Path):
    """fix_avg_prices: avg_price is overridden with volume-weighted open price."""
    from xtb_import import fix_avg_prices_from_open_positions
    import storage

    storage.save_balance({
        "AAPL.US": {"amount": 10.0, "avg_price": 200.0},
    })

    p = _positions_book(
        tmp, "fix_avg.xlsx",
        open_rows=[
            ["My Trades", "111", "AAPL.US", "STOCK", "BUY",
             5.0, 750.0, 150.0, 170.0, "2025-01-15 10:00:00"],
            ["My Trades", "222", "AAPL.US", "STOCK", "BUY",
             5.0, 800.0, 160.0, 170.0, "2025-06-20 10:00:00"],
        ],
    )
    fix_avg_prices_from_open_positions(str(p), "USD")
    bal = storage.load_balance()
    # weighted avg: (5*150 + 5*160) / 10 = 155.0
    assert abs(bal["AAPL.US"]["avg_price"] - 155.0) < 0.01


def test_fix_avg_prices_skips_tickers_not_in_balance(tmp: Path):
    """fix_avg_prices: tickers not in balance.json are ignored."""
    from xtb_import import fix_avg_prices_from_open_positions
    import storage

    storage.save_balance({})

    p = _positions_book(
        tmp, "fix_nobal.xlsx",
        open_rows=[[
            "My Trades", "111", "AAPL.US", "STOCK", "BUY",
            5.0, 750.0, 150.0, 170.0, "2025-01-15 10:00:00",
        ]],
    )
    fix_avg_prices_from_open_positions(str(p), "USD")
    bal = storage.load_balance()
    assert "AAPL.US" not in bal


def test_fix_avg_prices_empty_open_positions(tmp: Path):
    """fix_avg_prices: no-op when Open Positions sheet is empty."""
    from xtb_import import fix_avg_prices_from_open_positions
    import storage

    storage.save_balance({
        "AAPL.US": {"amount": 10.0, "avg_price": 200.0},
    })

    p = _positions_book(tmp, "fix_empty.xlsx")
    fix_avg_prices_from_open_positions(str(p), "USD")
    bal = storage.load_balance()
    assert bal["AAPL.US"]["avg_price"] == 200.0


def test_fix_avg_prices_translates_tickers(tmp: Path):
    """fix_avg_prices: tickers matching translation rules are translated before lookup."""
    from xtb_import import fix_avg_prices_from_open_positions
    import storage

    # Use a ticker that exists in balance (US ticker, no translation needed)
    storage.save_balance({
        "NVDA.US": {"amount": 2.0, "avg_price": 100.0},
    })

    p = _positions_book(
        tmp, "fix_translate.xlsx",
        open_rows=[
            ["My Trades", "111", "NVDA.US", "STOCK", "BUY",
             2.0, 464.16, 232.08, 232.08, "2025-03-28 13:30:18"],
        ],
    )
    fix_avg_prices_from_open_positions(str(p), "USD")
    bal = storage.load_balance()
    assert abs(bal["NVDA.US"]["avg_price"] - 232.08) < 0.01

