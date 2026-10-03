#!/usr/bin/env python3
"""Create a new user entry in users.json with a UUID key."""
from __future__ import annotations

import json
import sys
import uuid
from datetime import date
from pathlib import Path


USERS_PATH = Path(__file__).parent.parent / "data" / "users.json"


def create_user_entry(username: str) -> dict:
    """Create a new user entry with UUID key."""
    user_key = str(uuid.uuid4())
    return {
        user_key: {
            "user_name": username,
            "created": date.today().isoformat(),
        }
    }


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/create_user.py <username>")
        return 1

    username = sys.argv[1].strip()
    if not username:
        print("Error: Username cannot be empty")
        return 1

    # Load existing users
    if USERS_PATH.exists():
        with USERS_PATH.open("r", encoding="utf-8") as f:
            users = json.load(f)
    else:
        users = {}

    # Check if user already exists (by user_name)
    for data in users.values():
        if data.get("user_name") == username:
            print(f"Error: User '{username}' already exists")
            return 1

    # Create and add new user
    new_user = create_user_entry(username)
    users.update(new_user)

    # Write back
    USERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with USERS_PATH.open("w", encoding="utf-8") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)

    user_key = list(new_user.keys())[0]
    print(f"Created user '{username}' with key: {user_key}")
    return 0


if __name__ == "__main__":
    sys.exit(main())