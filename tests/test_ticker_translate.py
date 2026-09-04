"""Ticker translation — pytest suite (split from the original monolithic runner)."""

from __future__ import annotations

from pathlib import Path


def test_translate_no_rules(tmp: Path):
    """translate_ticker with no rules returns uppercased input."""
    from ticker_translate import translate_ticker
    assert translate_ticker("aapl") == "AAPL"
    assert translate_ticker("GOOG") == "GOOG"
    assert translate_ticker("", None) == ""


def test_translate_exact_match(tmp: Path):
    """Exact match rule replaces ticker."""
    from ticker_translate import translate_ticker
    rules = ["AMZN.DE=AMZ.DE", "VOW3.DE=VOW.DE"]
    assert translate_ticker("AMZN.DE", rules) == "AMZ.DE"
    assert translate_ticker("VOW3.DE", rules) == "VOW.DE"
    assert translate_ticker("AAPL.DE", rules) == "AAPL.DE"


def test_translate_suffix_swap(tmp: Path):
    """Suffix swap rule *.PL=*.WA replaces extension."""
    from ticker_translate import translate_ticker
    rules = ["*.PL=*.WA"]
    assert translate_ticker("SNT.PL", rules) == "SNT.WA"
    assert translate_ticker("CDR.PL", rules) == "CDR.WA"
    assert translate_ticker("AAPL.US", rules) == "AAPL.US"


def test_translate_xtb_country_rules(tmp: Path):
    """XTB country-code suffixes rewrite to Yahoo exchange suffixes."""
    from ticker_translate import translate_ticker
    rules = [
        "*.US=",
        "*.UK=*.L", "*.NL=*.AS", "*.FR=*.PA", "*.ES=*.MC",
        "*.AT=*.VI", "*.SE=*.ST", "*.GR=*.AT", "*.PL=*.WA",
    ]
    assert translate_ticker("SHEL.UK", rules) == "SHEL.L"
    assert translate_ticker("ASML.NL", rules) == "ASML.AS"
    assert translate_ticker("OR.FR", rules) == "OR.PA"
    assert translate_ticker("SAN.ES", rules) == "SAN.MC"
    assert translate_ticker("OMV.AT", rules) == "OMV.VI"
    assert translate_ticker("VOLV-B.SE", rules) == "VOLV-B.ST"
    assert translate_ticker("HTO.GR", rules) == "HTO.AT"   # result not re-matched
    assert translate_ticker("AAPL.US", rules) == "AAPL"
    assert translate_ticker("SAP.DE", rules) == "SAP.DE"   # same code, no rule


def test_translate_suffix_strip(tmp: Path):
    """Suffix strip rule .US= removes the suffix."""
    from ticker_translate import translate_ticker
    rules = [".US="]
    assert translate_ticker("AAPL.US", rules) == "AAPL"
    assert translate_ticker("GOOG.US", rules) == "GOOG"
    assert translate_ticker("AAPL.DE", rules) == "AAPL.DE"


def test_translate_no_match(tmp: Path):
    """No matching rule returns uppercased input."""
    from ticker_translate import translate_ticker
    rules = ["AMZN.DE=AMZ.DE", "*.PL=*.WA"]
    assert translate_ticker("MSFT", rules) == "MSFT"
    assert translate_ticker("AAPL.US", rules) == "AAPL.US"
