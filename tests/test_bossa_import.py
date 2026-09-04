"""BOSSA importer — pytest suite (split from the original monolithic runner)."""

from __future__ import annotations

from pathlib import Path


def test_bossa_validate_errors(tmp: Path):
    """validate_bossa_file catches empty and malformed files."""
    from bossa_import import validate_bossa_file

    empty = tmp / "empty.csv"
    empty.write_text("")
    valid, msg = validate_bossa_file(empty)
    assert not valid
    assert "empty" in msg.lower()

    wrong_cols = tmp / "wrong.csv"
    wrong_cols.write_text("name;value\ntest;123")
    valid, msg = validate_bossa_file(wrong_cols)
    assert not valid
    assert "missing" in msg.lower()

    valid_file = tmp / "valid.csv"
    valid_file.write_text("data;tytuł operacji;szczegóły;kwota;waluta\nrow1;row2;row3;row4;row5")
    valid, msg = validate_bossa_file(valid_file)
    assert valid


def test_bossa_validate_valid(tmp: Path):
    """validate_bossa_file: valid CSV with required columns passes."""
    from bossa_import import validate_bossa_file
    csv_content = "data;tytuł operacji;szczegóły;kwota;waluta\n2023-01-03;test;;;PLN\n"
    p = tmp / "test.csv"
    p.write_text(csv_content, encoding="utf-8")
    valid, msg = validate_bossa_file(p)
    assert valid is True


def test_bossa_validate_empty(tmp: Path):
    """validate_bossa_file: empty file fails."""
    from bossa_import import validate_bossa_file
    p = tmp / "empty.csv"
    p.write_text("", encoding="utf-8")
    valid, msg = validate_bossa_file(p)
    assert valid is False


def test_bossa_validate_missing_columns(tmp: Path):
    """validate_bossa_file: missing required columns fails."""
    from bossa_import import validate_bossa_file
    csv_content = "col1;col2;col3\n"
    p = tmp / "bad.csv"
    p.write_text(csv_content, encoding="utf-8")
    valid, msg = validate_bossa_file(p)
    assert valid is False
    assert "Missing required columns" in msg


def test_bossa_parse_float_basic(tmp: Path):
    """_parse_float: normal number parsing."""
    from bossa_import import _parse_float
    assert _parse_float("123.45") == 123.45
    assert _parse_float("123,45") == 123.45
    assert _parse_float("-50.0") == -50.0


def test_bossa_parse_float_empty(tmp: Path):
    """_parse_float: empty/None returns None."""
    from bossa_import import _parse_float
    assert _parse_float("") is None
    assert _parse_float(None) is None


def test_bossa_parse_float_invalid(tmp: Path):
    """_parse_float: non-numeric returns None."""
    from bossa_import import _parse_float
    assert _parse_float("abc") is None
    assert _parse_float("  ") is None


def test_bossa_read_csv_utf8(tmp: Path):
    """_read_csv_text: reads UTF-8 file."""
    from bossa_import import _read_csv_text
    p = tmp / "test.csv"
    p.write_text("data;kwota\n100;200\n", encoding="utf-8")
    text = _read_csv_text(p)
    assert "data;kwota" in text


def test_bossa_read_csv_windows1250(tmp: Path):
    """_read_csv_text: reads Windows-1250 encoded file."""
    from bossa_import import _read_csv_text
    p = tmp / "test.csv"
    content = "data;tytuł\n"
    p.write_bytes(content.encode("windows-1250"))
    text = _read_csv_text(p)
    assert "data;tytuł" in text


def test_bossa_parse_buy(tmp: Path):
    """parse_bossa_csv: buy transaction creates two entries."""
    from bossa_import import parse_bossa_csv
    import bossa_import

    original_resolve = bossa_import.resolve_isins_with_names
    bossa_import.resolve_isins_with_names = lambda names, progress_cb=None: (
        {isin: "AAPL.US" for isin in names}, {}
    )
    try:
        csv_content = (
            "data;tytuł operacji;szczegóły;kwota;waluta\n"
            "2023-01-03;Rozliczenie transakcji kupna;Apple Inc. (US0378331005) 10 x 125.07 USD nr 1;-1250.70;USD\n"
        )
        p = tmp / "buy.csv"
        p.write_text(csv_content, encoding="utf-8")
        txns, unresolved = parse_bossa_csv(p, "PLN")
        assert len(txns) == 1
        assert txns[0]["date"] == "2023-01-03"
        tickers = {e["ticker"] for e in txns[0]["entries"]}
        assert "AAPL.US" in tickers
        assert "USD" in tickers
    finally:
        bossa_import.resolve_isins_with_names = original_resolve


def test_bossa_parse_sell(tmp: Path):
    """parse_bossa_csv: sell transaction creates entries with negative shares.

    Import is rejected with a clear error telling the user to manually add
    a corporate-action entry (e.g. split/spin-off) before importing.
    """
    from bossa_import import parse_bossa_csv
    from ledger_core import find_negative_positions
    import bossa_import

    original_resolve = bossa_import.resolve_isins_with_names
    bossa_import.resolve_isins_with_names = lambda names, progress_cb=None: (
        {isin: "AAPL.US" for isin in names}, {}
    )
    try:
        csv_content = (
            "data;tytuł operacji;szczegóły;kwota;waluta\n"
            "2023-06-01;Rozliczenie transakcji sprzedaży;Apple Inc. (US0378331005) 5 x 180.09 USD nr 2;900.45;USD\n"
        )
        p = tmp / "sell.csv"
        p.write_text(csv_content, encoding="utf-8")
        txns, _ = parse_bossa_csv(p, "PLN")
        # Import should be rejected because AAPL.US has no buy to cover the sell
        negatives = find_negative_positions(txns)
        assert len(negatives) == 1
        ticker, missing, first_neg_date = negatives[0]
        assert ticker == "AAPL.US"
        assert missing == 5.0
        assert first_neg_date == "2023-06-01"
    finally:
        bossa_import.resolve_isins_with_names = original_resolve


def test_bossa_parse_deposit(tmp: Path):
    """parse_bossa_csv: deposit marked as account_operation."""
    from bossa_import import parse_bossa_csv

    csv_content = (
        "data;tytuł operacji;szczegóły;kwota;waluta\n"
        "2023-01-03;Przelew do DM BOŚ;;5000.00;PLN\n"
    )
    p = tmp / "deposit.csv"
    p.write_text(csv_content, encoding="utf-8")
    txns, _ = parse_bossa_csv(p, "PLN")
    assert len(txns) == 1
    assert txns[0]["entries"][0].get("account_operation") is True
    assert txns[0]["entries"][0]["amount"] == 5000.0


def test_bossa_parse_short_row_skipped(tmp: Path):
    """parse_bossa_csv: rows with fewer than 5 columns are skipped."""
    from bossa_import import parse_bossa_csv

    csv_content = (
        "data;tytuł operacji;szczegóły;kwota;waluta\n"
        "2023-01-03;short row\n"
    )
    p = tmp / "short.csv"
    p.write_text(csv_content, encoding="utf-8")
    txns, _ = parse_bossa_csv(p, "PLN")
    assert len(txns) == 0


def test_bossa_dividend_import(tmp: Path):
    """parse_bossa_csv: dividend rows are imported as cash credits."""
    from bossa_import import parse_bossa_csv

    csv_content = (
        "data;tytuł operacji;szczegóły;kwota;waluta\n"
        "2023-06-15;Dywidenda;AAPL dividend;25.30;USD\n"
    )
    p = tmp / "dividend.csv"
    p.write_text(csv_content, encoding="utf-8")
    txns, _ = parse_bossa_csv(p, "USD")
    assert len(txns) == 1
    entries = txns[0]["entries"]
    assert len(entries) == 1
    assert entries[0]["ticker"] == "USD"
    assert entries[0]["amount"] == 25.30
    assert entries[0].get("account_operation") is None
