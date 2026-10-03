#!/usr/bin/env python3
"""Create a new user entry in users.json with a UUID key.

Uses storage backend (local or R2 via COS_* env vars).
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date
from pathlib import Path

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import storage


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/create_user.py <username>")
        return 1

    username = sys.argv[1].strip()
    if not username:
        print("Error: Username cannot be empty")
        return 1

    # Check if user already exists
    for user_key, data in storage._load_users().items():
        if data.get("user_name") == username:
            print(f"Error: User '{username}' already exists")
            return 1

    # Create and add new user via storage (uses R2 if COS_* env vars set)
    user_key = str(uuid.uuid4())
    storage._save_users({
        **storage._load_users(),
        user_key: {"user_name": username, "created": date.today().isoformat()},
    })

    print(f"Created user '{username}' with key: {user_key}")
    print(f"Stored in: {'R2' if os.getenv('COS_BUCKET') else 'local filesystem'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())