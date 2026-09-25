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
        statement = parse_bossa_csv(p, "PLN")
        txns = statement.transactions
        assert len(txns) == 1
        assert txns[0]["date"] == "2023-01-03"
        tickers = {e["ticker"] for e in txns[0]["entries"]}
        assert "AAPL.US" in tickers
        assert "USD" in tickers
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
    statement = parse_bossa_csv(p, "PLN")
    assert len(statement.transactions) == 1
    assert statement.transactions[0]["entries"][0].get("account_operation") is True
    assert statement.transactions[0]["entries"][0]["amount"] == 5000.0


def test_bossa_parse_short_row_skipped(tmp: Path):
    """parse_bossa_csv: rows with fewer than 5 columns are skipped."""
    from bossa_import import parse_bossa_csv

    csv_content = (
        "data;tytuł operacji;szczegóły;kwota;waluta\n"
        "2023-01-03;short row\n"
    )
    p = tmp / "short.csv"
    p.write_text(csv_content, encoding="utf-8")
    statement = parse_bossa_csv(p, "PLN")
    assert len(statement.transactions) == 0
    assert statement.skipped.get("short_row") == 1


def test_bossa_dividend_import(tmp: Path):
    """parse_bossa_csv: dividend rows are imported as cash credits."""
    from bossa_import import parse_bossa_csv

    csv_content = (
        "data;tytuł operacji;szczegóły;kwota;waluta\n"
        "2023-06-15;Dywidenda;AAPL dividend;25.30;USD\n"
    )
    p = tmp / "dividend.csv"
    p.write_text(csv_content, encoding="utf-8")
    statement = parse_bossa_csv(p, "USD")
    assert len(statement.transactions) == 1
    entries = statement.transactions[0]["entries"]
    assert len(entries) == 1
    assert entries[0]["ticker"] == "USD"
    assert entries[0]["amount"] == 25.30
    assert entries[0].get("account_operation") is None


def test_bossa_fx_swap_is_not_account_operation(tmp: Path):
    """FX swaps are conversions, not deposits — they must not count as invested capital."""
    from bossa_import import parse_bossa_csv

    csv_content = (
        "data;tytuł operacji;szczegóły;kwota;waluta\n"
        "2026-04-16;Wymiana waluty PLN/EUR 4.2385;;4246,75;EUR\n"
        "2026-04-16;Wymiana waluty PLN/EUR 4.2385;;-18000,00;PLN\n"
    )
    p = tmp / "fx.csv"
    p.write_text(csv_content, encoding="utf-8")
    statement = parse_bossa_csv(p)

    assert len(statement.transactions) == 1
    entries = statement.transactions[0]["entries"]
    assert len(entries) == 2
    assert all(e.get("account_operation") is None for e in entries)
    assert {e["ticker"]: e["amount"] for e in entries} == {"EUR": 4246.75, "PLN": -18000.0}
    # A paired swap is not worth warning about.
    assert not any("FX swap" in w for w in statement.warnings)


def test_bossa_fx_swap_unpaired_leg_warns(tmp: Path):
    """An FX swap missing one leg is reported instead of silently imported."""
    from bossa_import import parse_bossa_csv

    csv_content = (
        "data;tytuł operacji;szczegóły;kwota;waluta\n"
        "2026-04-16;Wymiana waluty PLN/EUR 4.2385;;4246,75;EUR\n"
    )
    p = tmp / "fx_one_leg.csv"
    p.write_text(csv_content, encoding="utf-8")
    statement = parse_bossa_csv(p)
    assert len(statement.transactions) == 1
    assert any("expected 2 legs, found 1" in w for w in statement.warnings)


def test_bossa_import_bossa_fx_lands_unmarked(tmp: Path):
    """import_bossa: FX legs reach the ledger without account_operation."""
    from bossa_import import import_bossa
    from ledger_core import get_all_transactions

    csv_content = (
        "data;tytuł operacji;szczegóły;kwota;waluta\n"
        "2026-04-16;Wymiana waluty PLN/EUR 4.2385;;4246,75;EUR\n"
        "2026-04-16;Wymiana waluty PLN/EUR 4.2385;;-18000,00;PLN\n"
    )
    p = tmp / "fx_import.csv"
    p.write_text(csv_content, encoding="utf-8")
    res = import_bossa(p)
    assert res["success"] is True
    assert res["imported"] == 1

    entries = get_all_transactions()[0]["entries"]
    assert all("account_operation" not in e for e in entries)


def test_bossa_normalises_polish_dates(tmp: Path):
    """dd.mm.yyyy dates are normalised to ISO, not written through verbatim."""
    from bossa_import import parse_bossa_csv

    csv_content = (
        "data;tytuł operacji;szczegóły;kwota;waluta\n"
        "15.05.2026;Przelew do DM BOŚ;;100,00;PLN\n"
        "02.01.2026;Przelew do DM BOŚ;;200,00;PLN\n"
    )
    p = tmp / "dates.csv"
    p.write_text(csv_content, encoding="utf-8")
    statement = parse_bossa_csv(p)
    assert [t["date"] for t in statement.transactions] == ["2026-01-02", "2026-05-15"]


def test_bossa_bad_date_is_reported(tmp: Path):
    """An unparseable date is skipped and reported, not silently written to the ledger."""
    from bossa_import import parse_bossa_csv

    csv_content = (
        "data;tytuł operacji;szczegóły;kwota;waluta\n"
        "not-a-date;Przelew do DM BOŚ;;100,00;PLN\n"
    )
    p = tmp / "bad_date.csv"
    p.write_text(csv_content, encoding="utf-8")
    statement = parse_bossa_csv(p)
    assert statement.transactions == []
    assert statement.skipped.get("bad_date") == 1
    assert any("unreadable date" in w for w in statement.warnings)


def test_bossa_missing_currency_never_invents_a_ticker(tmp: Path):
    """A blank waluta column must not fall back to a fake 'MANY'/'USD' cash ticker."""
    from bossa_import import parse_bossa_csv

    csv_content = (
        "data;tytuł operacji;szczegóły;kwota;waluta\n"
        "2026-01-02;Przelew do DM BOŚ;;100,00;\n"
    )
    p = tmp / "no_ccy.csv"
    p.write_text(csv_content, encoding="utf-8")
    statement = parse_bossa_csv(p, "Many")
    assert statement.transactions == []
    assert statement.skipped.get("no_currency") == 1
    assert any("no currency" in w for w in statement.warnings)


def test_bossa_uses_waluta_column_over_fallback(tmp: Path):
    """The per-row waluta column wins over any caller-supplied fallback currency."""
    from bossa_import import parse_bossa_csv

    csv_content = (
        "data;tytuł operacji;szczegóły;kwota;waluta\n"
        "2026-01-02;Przelew do DM BOŚ;;100,00;EUR\n"
    )
    p = tmp / "waluta.csv"
    p.write_text(csv_content, encoding="utf-8")
    statement = parse_bossa_csv(p, "PLN")
    assert statement.transactions[0]["entries"][0]["ticker"] == "EUR"


def test_bossa_unknown_operation_is_reported(tmp: Path):
    """An unrecognised operation title is surfaced, not dropped in silence."""
    from bossa_import import parse_bossa_csv

    csv_content = (
        "data;tytuł operacji;szczegóły;kwota;waluta\n"
        "2026-01-02;Opłata za obsługę rachunku;;-12,50;PLN\n"
    )
    p = tmp / "unknown.csv"
    p.write_text(csv_content, encoding="utf-8")
    statement = parse_bossa_csv(p)
    assert statement.transactions == []
    assert statement.skipped.get("unknown_operation") == 1
    assert any("unrecognised operation" in w for w in statement.warnings)


def test_bossa_unreadable_trade_details_is_reported(tmp: Path):
    """A buy row whose details cannot be parsed is reported instead of dropped."""
    from bossa_import import parse_bossa_csv

    csv_content = (
        "data;tytuł operacji;szczegóły;kwota;waluta\n"
        "2026-01-02;Rozliczenie transakcji kupna:;Apple Inc. (US0378331005) 10 szt.;-1250,70;PLN\n"
    )
    p = tmp / "bad_details.csv"
    p.write_text(csv_content, encoding="utf-8")
    statement = parse_bossa_csv(p)
    assert statement.transactions == []
    assert statement.skipped.get("unreadable_details") == 1
    assert any("cannot read trade details" in w for w in statement.warnings)


def test_bossa_unresolved_isin_surfaces_as_warning(tmp: Path):
    """Unmapped ISINs are reported as a warning on an otherwise successful import."""
    from bossa_import import import_bossa

    csv_content = (
        "data;tytuł operacji;szczegóły;kwota;waluta\n"
        "2026-01-02;Rozliczenie transakcji kupna:;"
        "Unknown Fund (DE0005793303) 10 x 100.00 PLN nr 1;-1000,00;PLN\n"
    )
    p = tmp / "unresolved.csv"
    p.write_text(csv_content, encoding="utf-8")
    res = import_bossa(p)
    assert res["success"] is True
    assert res["imported"] == 0
    assert any("DE0005793303" in w for w in res["warnings"])
    assert any("ISIN mappings" in w for w in res["warnings"])


def test_bossa_parse_float_thousands_separators(tmp: Path):
    """_parse_float handles Polish grouping and mixed decimal separators."""
    from bossa_import import _parse_float

    assert _parse_float("1 234,56") == 1234.56
    assert _parse_float("1 234,56") == 1234.56  # non-breaking space
    assert _parse_float("1.234,56") == 1234.56
    assert _parse_float("-1.234,00") == -1234.00
    assert _parse_float("16.488") == 16.488


def test_bossa_parse_date_formats():
    """_parse_date normalises every date shape BOSSA exports."""
    from bossa_import import _parse_date

    assert _parse_date("2026-05-15") == "2026-05-15"
    assert _parse_date("15.05.2026") == "2026-05-15"
    assert _parse_date("15/05/2026") == "2026-05-15"
    assert _parse_date("2026-05-15 10:22:31") == "2026-05-15"
    assert _parse_date("2026-05-15T10:22:31") == "2026-05-15"
    assert _parse_date("") is None
    assert _parse_date("31/31/2026") is None


def test_bossa_refund_is_account_operation(tmp: Path):
    """'Zwrot nadpłaty' refunds count as account operations."""
    from bossa_import import parse_bossa_csv

    csv_content = (
        "data;tytuł operacji;szczegóły;kwota;waluta\n"
        "2026-01-02;Zwrot nadpłaty - przekroczony limit wpłat na IKE/IKZE 836368;;-250,00;PLN\n"
    )
    p = tmp / "refund.csv"
    p.write_text(csv_content, encoding="utf-8")
    statement = parse_bossa_csv(p)
    entry = statement.transactions[0]["entries"][0]
    assert entry["ticker"] == "PLN"
    assert entry["amount"] == -250.00
    assert entry["account_operation"] is True
