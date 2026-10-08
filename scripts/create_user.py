#!/usr/bin/env python3
"""Create a new user entry in users.json with a UUID key.

Always uses local filesystem storage (users.json stays local).
"""
from __future__ import annotations

import sys
import uuid
from datetime import date
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import storage


def print_boxed(text: str, width: int = 60) -> None:
    """Print text in a nice box."""
    print("┌" + "─" * width + "┐")
    for line in text.split("\n"):
        padding = width - len(line)
        print(f"│ {line}{' ' * padding} │")
    print("└" + "─" * width + "┘")


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/create_user.py <username>")
        return 1

    username = sys.argv[1].strip()
    if not username:
        print("Error: Username cannot be empty")
        return 1

    # Check if user already exists
    users = storage._load_users()
    for user_key, data in users.items():
        if data.get("user_name") == username:
            print(f"Error: User '{username}' already exists")
            return 1

    # Create and add new user (always local filesystem)
    user_key = str(uuid.uuid4())
    new_user = {"user_name": username, "created": date.today().isoformat()}
    users[user_key] = new_user
    storage._save_users(users)

    print_boxed(
        f"User Created Successfully!\n\n"
        f"  Username:  {username}\n"
        f"  User Key:  {user_key}\n"
        f"  Created:   {date.today().isoformat()}\n\n"
        f"Storage:  Local filesystem (users.json)\n"
        f"Users:    {len(users)} total"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())