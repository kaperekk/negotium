#!/usr/bin/env python3
"""Download a file from COS (R2) to local."""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from storage.backends import get_backend


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/download_from_cos.py <key> [output_path]")
        print("Example: python scripts/download_from_cos.py users.json")
        print("Example: python scripts/download_from_cos.py users.json data/users.json")
        return 1

    key = sys.argv[1]
    output = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(key)

    backend = get_backend()
    if not backend.exists(key):
        print(f"Error: Key '{key}' not found in storage")
        return 1

    data = backend.read_bytes(key)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)
    print(f"Downloaded {key} -> {output} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())