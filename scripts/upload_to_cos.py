#!/usr/bin/env python3
"""Upload a local file to COS (R2)."""
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
    if len(sys.argv) < 3:
        print("Usage: python scripts/upload_to_cos.py <local_file> <key>")
        print("Example: python scripts/upload_to_cos.py data/users.json users.json")
        return 1

    local_path = Path(sys.argv[1])
    key = sys.argv[2]

    if not local_path.exists():
        print(f"Error: Local file '{local_path}' not found")
        return 1

    backend = get_backend()
    data = local_path.read_bytes()
    backend.write_bytes(key, data)
    print(f"Uploaded {local_path} -> {key} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())