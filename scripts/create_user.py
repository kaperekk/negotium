#!/usr/bin/env python3
"""Create a new user with UUID access key. Stores mapping in data/keys.json."""

import json
import sys
import uuid
from pathlib import Path
from datetime import date

ROOT = Path(__file__).parent.parent
DATA_ROOT = ROOT / "data"
KEYS_FILE = DATA_ROOT / "keys.json"
USERS_FILE = DATA_ROOT / "users.json"


def load_json(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def create_user(name: str) -> str:
    keys = load_json(KEYS_FILE)
    users = load_json(USERS_FILE)

    # Generate UUID key
    key = str(uuid.uuid4())
    user_id = f"user_{len(users) + 1:03d}"

    # Check for duplicate name
    for u in users.values():
        if u.get("name") == name:
            print(f"User with name '{name}' already exists", file=sys.stderr)
            sys.exit(1)

    # Update keys.json (key -> user_id)
    keys[key] = user_id
    save_json(KEYS_FILE, keys)

    # Update users.json (user_id -> metadata)
    users[user_id] = {
        "name": name,
        "created": date.today().isoformat(),
        "key": key
    }
    save_json(USERS_FILE, users)

    # Create user directory structure
    user_dir = DATA_ROOT / "users" / user_id
    (user_dir / "projects").mkdir(parents=True, exist_ok=True)
    (user_dir / "projects.json").write_text("{}", encoding="utf-8")
    (user_dir / "config.json").write_text(
        json.dumps({"default_currency": "PLN", "theme": "dark", "ticker_rules": [], "isin_tickers": []}, indent=2),
        encoding="utf-8"
    )

    print(f"Created user: {name}")
    print(f"User ID: {user_id}")
    print(f"Access key: {key}")
    print(f"\nGive this key to the user. They will enter it on first app load.")
    return key


def list_users() -> None:
    users = load_json(USERS_FILE)
    if not users:
        print("No users yet")
        return
    for uid, info in users.items():
        print(f"  {uid}: {info['name']} (created {info['created']})")


def revoke_user(user_id: str) -> None:
    keys = load_json(KEYS_FILE)
    users = load_json(USERS_FILE)

    if user_id not in users:
        print(f"User {user_id} not found", file=sys.stderr)
        sys.exit(1)

    # Remove key mapping
    key_to_remove = None
    for k, v in keys.items():
        if v == user_id:
            key_to_remove = k
            break
    if key_to_remove:
        del keys[key_to_remove]
        save_json(KEYS_FILE, keys)

    # Remove user
    del users[user_id]
    save_json(USERS_FILE, users)

    print(f"Revoked user: {user_id}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python scripts/create_user.py create \"User Name\"")
        print("  python scripts/create_user.py list")
        print("  python scripts/create_user.py revoke user_001")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "create":
        if len(sys.argv) < 3:
            print("Usage: python scripts/create_user.py create \"User Name\"")
            sys.exit(1)
        create_user(sys.argv[2])
    elif cmd == "list":
        list_users()
    elif cmd == "revoke":
        if len(sys.argv) < 3:
            print("Usage: python scripts/create_user.py revoke user_001")
            sys.exit(1)
        revoke_user(sys.argv[2])
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)