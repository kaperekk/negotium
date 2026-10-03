"""
backends.py — Storage backend abstraction for local filesystem and S3-compatible storage.
"""
from __future__ import annotations

import os
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO, Iterator, Optional
from urllib.parse import urlparse

try:
    import boto3
    from botocore.config import Config as BotoConfig
    from botocore.exceptions import ClientError
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False
    boto3 = None
    ClientError = Exception


class StorageBackend(ABC):
    """Abstract base class for storage backends."""

    @abstractmethod
    def exists(self, path: str) -> bool:
        """Check if a path exists."""
        pass

    @abstractmethod
    def read_bytes(self, path: str) -> bytes:
        """Read entire file as bytes."""
        pass

    @abstractmethod
    def write_bytes(self, path: str, data: bytes) -> None:
        """Write bytes to path (atomic if possible)."""
        pass

    @abstractmethod
    def delete(self, path: str) -> None:
        """Delete a file."""
        pass

    @abstractmethod
    def list_files(self, prefix: str) -> list[str]:
        """List files under a prefix."""
        pass

    @abstractmethod
    def mkdir(self, path: str) -> None:
        """Create directory (noop for object storage)."""
        pass

    @abstractmethod
    def open_read(self, path: str) -> BinaryIO:
        """Open file for reading."""
        pass

    @abstractmethod
    def open_write(self, path: str) -> BinaryIO:
        """Open file for writing."""
        pass


class LocalBackend(StorageBackend):
    """Local filesystem storage backend."""

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _full_path(self, path: str) -> Path:
        return self.root / path

    def exists(self, path: str) -> bool:
        return self._full_path(path).exists()

    def read_bytes(self, path: str) -> bytes:
        return self._full_path(path).read_bytes()

    def write_bytes(self, path: str, data: bytes) -> None:
        full = self._full_path(path)
        full.parent.mkdir(parents=True, exist_ok=True)
        tmp = full.with_name(full.name + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(full)

    def delete(self, path: str) -> None:
        full = self._full_path(path)
        if full.exists():
            full.unlink()

    def list_files(self, prefix: str) -> list[str]:
        full = self._full_path(prefix)
        if not full.exists():
            return []
        if full.is_file():
            return [prefix]
        return [
            str(p.relative_to(self.root))
            for p in full.rglob("*")
            if p.is_file()
        ]

    def mkdir(self, path: str) -> None:
        self._full_path(path).mkdir(parents=True, exist_ok=True)

    def open_read(self, path: str) -> BinaryIO:
        return self._full_path(path).open("rb")

    def open_write(self, path: str) -> BinaryIO:
        full = self._full_path(path)
        full.parent.mkdir(parents=True, exist_ok=True)
        return full.open("wb")


class S3Backend(StorageBackend):
    """S3-compatible storage backend (AWS S3, Cloudflare R2, MinIO, etc.)."""

    def __init__(
        self,
        bucket: str,
        endpoint_url: Optional[str] = None,
        region_name: str = "auto",
        access_key_id: Optional[str] = None,
        secret_access_key: Optional[str] = None,
        prefix: str = "",
    ):
        if not BOTO3_AVAILABLE:
            raise RuntimeError("boto3 not installed. Run: pip install boto3")

        self.bucket = bucket
        self.prefix = prefix.rstrip("/") + "/" if prefix else ""
        self._lock = threading.Lock()

        session = boto3.session.Session()
        self.client = session.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region_name,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            config=BotoConfig(
                retries={"max_attempts": 3, "mode": "adaptive"},
                connect_timeout=10,
                read_timeout=30,
            ),
        )

    def _key(self, path: str) -> str:
        return f"{self.prefix}{path.lstrip('/')}"

    def exists(self, path: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=self._key(path))
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            raise

    def read_bytes(self, path: str) -> bytes:
        try:
            resp = self.client.get_object(Bucket=self.bucket, Key=self._key(path))
            return resp["Body"].read()
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                raise FileNotFoundError(f"Key not found: {path}")
            raise

    def write_bytes(self, path: str, data: bytes) -> None:
        self.client.put_object(Bucket=self.bucket, Key=self._key(path), Body=data)

    def delete(self, path: str) -> None:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=self._key(path))
        except ClientError as e:
            if e.response["Error"]["Code"] != "404":
                raise

    def list_files(self, prefix: str) -> list[str]:
        full_prefix = self._key(prefix)
        files = []
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=full_prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.startswith(self.prefix):
                    files.append(key[len(self.prefix):])
        return files

    def mkdir(self, path: str) -> None:
        pass

    def open_read(self, path: str) -> BinaryIO:
        resp = self.client.get_object(Bucket=self.bucket, Key=self._key(path))
        return resp["Body"]

    def open_write(self, path: str) -> BinaryIO:
        return _S3WriteStream(self.client, self.bucket, self._key(path))


class _S3WriteStream:
    """File-like object for streaming writes to S3."""

    def __init__(self, client, bucket: str, key: str):
        self._client = client
        self._bucket = bucket
        self._key = key
        self._buffer = bytearray()
        self._closed = False

    def write(self, data: bytes) -> int:
        if self._closed:
            raise ValueError("I/O operation on closed file")
        self._buffer.extend(data)
        return len(data)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        if not self._closed:
            self._client.put_object(Bucket=self._bucket, Key=self._key, Body=bytes(self._buffer))
            self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


_backend: StorageBackend | None = None
_backend_lock = threading.Lock()


def get_backend() -> StorageBackend:
    """Get the global storage backend (initialized on first call)."""
    global _backend
    if _backend is None:
        with _backend_lock:
            if _backend is None:
                _backend = _create_backend_from_env()
    return _backend


def set_backend(backend: StorageBackend) -> None:
    """Set the global storage backend (for testing or explicit config)."""
    global _backend
    with _backend_lock:
        _backend = backend


def _create_backend_from_env() -> StorageBackend:
    """Create backend from environment variables / Streamlit secrets."""
    import streamlit as st

    # Check for S3-compatible config in Streamlit secrets
    try:
        cos_config = st.secrets.get("cos", {})
    except Exception:
        cos_config = {}

    # Also check environment variables as fallback
    bucket = cos_config.get("bucket") or os.getenv("COS_BUCKET")
    endpoint = cos_config.get("endpoint") or os.getenv("COS_ENDPOINT")
    region = cos_config.get("region") or os.getenv("COS_REGION", "auto")
    access_key = cos_config.get("access_key") or os.getenv("COS_ACCESS_KEY")
    secret_key = cos_config.get("secret_key") or os.getenv("COS_SECRET_KEY")
    prefix = cos_config.get("prefix") or os.getenv("COS_PREFIX", "")

    if bucket and access_key and secret_key:
        return S3Backend(
            bucket=bucket,
            endpoint_url=endpoint,
            region_name=region,
            access_key_id=access_key,
            secret_access_key=secret_key,
            prefix=prefix,
        )

    # Default to local filesystem
    from storage.context import DATA_ROOT
    return LocalBackend(DATA_ROOT)