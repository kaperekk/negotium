"""
ticker_translate.py — Ticker symbol translation layer

Rules format (one per line, evaluated top-to-bottom, first match wins):
  AMZN.DE=AMZ.DE   → exact match
  *.PL=*.WA         → suffix swap: SNT.PL → SNT.WA
  .US=              → strip suffix: AAPL.US → AAPL
"""
from __future__ import annotations


def translate_ticker(ticker: str, rules: list[str] | None = None) -> str:
    upper = ticker.upper()
    if not rules:
        return upper
    for rule in rules:
        if "=" not in rule:
            continue
        left, right = rule.split("=", 1)
        left, right = left.strip(), right.strip()

        if left.startswith("*."):
            suffix = left[1:]
            if upper.endswith(suffix):
                base = upper[: -len(suffix)]
                if right.startswith("*."):
                    return base + right[1:]
                return base + right if right else base
        elif left.startswith("."):
            if upper.endswith(left):
                base = upper[: -len(left)]
                return base + right if right else base
        else:
            if upper == left:
                return right if right else upper
    return upper
