#!/usr/bin/env python3
"""Upload users.json to COS (Cloudflare R2 / S3-compatible).

Run this after creating users locally if you want the user registry in COS.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    print("Error: python-dotenv not installed. Run: pip install python-dotenv")
    sys.exit(1)

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import os
import storage
from storage.backends import S3Backend


def main() -> int:
    # Check COS credentials
    bucket = os.getenv("COS_BUCKET")
    access_key = os.getenv("COS_ACCESS_KEY")
    secret_key = os.getenv("COS_SECRET_KEY")

    if not (bucket and access_key and secret_key):
        print("Error: COS credentials not found in .env")
        print("Required: COS_BUCKET, COS_ACCESS_KEY, COS_SECRET_KEY")
        return 1

    endpoint = os.getenv("COS_ENDPOINT")
    region = os.getenv("COS_REGION", "auto")
    prefix = os.getenv("COS_PREFIX", "")

    # Read local users.json
    users_data = storage._load_users()
    if not users_data:
        print("No users found in local users.json")
        return 1

    # Create S3 backend
    try:
        s3 = S3Backend(
            bucket=bucket,
            endpoint_url=endpoint,
            region_name=region,
            access_key_id=access_key,
            secret_access_key=secret_key,
            prefix=prefix,
        )
    except Exception as e:
        print(f"Error creating S3 client: {e}")
        return 1

    # Upload users.json
    key = f"users.json".lstrip("/")
    import json
    s3.write_bytes(key, json.dumps(users_data, indent=2, ensure_ascii=False).encode())

    print(f"Uploaded {len(users_data)} user(s) to COS:")
    for user_key, data in users_data.items():
        print(f"  - {data.get('user_name')} ({user_key})")
    print(f"Location: s3://{bucket}/{key}")

    return 0


if __name__ == "__main__":
    sys.exit(main())