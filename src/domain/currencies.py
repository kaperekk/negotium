"""
currencies.py — single source of truth for currency handling.

Every currency list, exchange-suffix map, triangulation rule and display
symbol lives here. Adding a new base currency means touching ONLY this
module (plus config ticker_rules if Yahoo needs a symbol mapping).
"""
from __future__ import annotations

# Currencies that can be held as cash in the ledger / chosen as base currency.
SUPPORTED_CURRENCIES: frozenset[str] = frozenset({"USD", "EUR", "PLN"})

# Yahoo exchange suffix → trading currency.
CURRENCY_SUFFIXES: dict[str, list[str]] = {
    "EUR": [".DE", ".F", ".PA", ".MI", ".AS", ".BR", ".LS", ".MC", ".VI", ".IR", ".HE", ".AT"],
    "GBP": [".L"],
    "MXN": [".MX"],
    "CAD": [".TO"],
    "AUD": [".AX"],
    "HKD": [".HK"],
    "JPY": [".T"],
    "KRW": [".KS"],
    "CNY": [".SS", ".SZ"],
    "SGD": [".SG", ".SI"],
    "CHF": [".SW"],
    "BRL": [".SA"],
    "PLN": [".WA"],
    "SEK": [".ST"],
    "NOK": [".OL"],
    "DKK": [".CO"],
    "CZK": [".PR"],
    "HUF": [".BD"],
    "TRY": [".IS"],
}

# Exchange suffix → currency lookup (derived — do not edit by hand).
SUFFIX_CURRENCY: dict[str, str] = {
    s: ccy for ccy, suffixes in CURRENCY_SUFFIXES.items() for s in suffixes
}

# Currencies whose Yahoo {CCY}PLN=X pair has no historical daily data (the
# chart API returns zero points for them — verified per pair). Their FX is
# triangulated via USD: {CCY}USD=X × USDPLN=X, both of which Yahoo serves.
TRIANGULATE_VIA_USD: frozenset[str] = frozenset({
    "MXN", "HUF",   # original set
    "CAD", "KRW", "CNY", "BRL", "SEK", "NOK", "CZK", "TRY",  # no {CCY}PLN history
})

# Display symbols per base currency (UI).
CURRENCY_SYMBOLS: dict[str, str] = {"PLN": " PLN", "EUR": "€", "USD": "$"}
