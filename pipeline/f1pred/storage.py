"""A tiny key/value store over either a local directory or a Cloud Storage bucket."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import settings

_SEEDED = ("data/history.parquet", "cache/", "models/")


class Store:
    def __init__(self, uri: str | None = None):
        uri = uri or settings.store_uri
        self.uri = uri
        if uri.startswith("gs://"):
            from google.cloud import storage  # imported lazily so local runs don't need GCP auth

            bucket_name, _, prefix = uri[5:].partition("/")
            self._bucket = storage.Client().bucket(bucket_name)
            self._prefix = prefix.strip("/")
            self._root = None
        else:
            self._bucket = None
            self._root = Path(uri)

    def _key(self, key: str) -> str:
        return f"{self._prefix}/{key}" if self._prefix else key

    def read_bytes(self, key: str) -> bytes | None:
        if self._bucket is not None:
            blob = self._bucket.blob(self._key(key))
            data = blob.download_as_bytes() if blob.exists() else None
        else:
            path = self._root / key
            data = path.read_bytes() if path.exists() else None
        if data is None and settings.seed_dir and key.startswith(_SEEDED):
            # First run in a fresh bucket: start from the history, timing cache and models shipped in the image.
            seeded = settings.seed_dir / key
            data = seeded.read_bytes() if seeded.exists() else None
        return data

    def write_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        if self._bucket is not None:
            blob = self._bucket.blob(self._key(key))
            blob.cache_control = "public, max-age=60"
            blob.upload_from_string(data, content_type=content_type)
            return
        path = self._root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def read_json(self, key: str) -> Any | None:
        data = self.read_bytes(key)
        return json.loads(data) if data is not None else None

    def write_json(self, key: str, value: Any) -> None:
        body = json.dumps(value, separators=(",", ":"), default=str).encode()
        self.write_bytes(key, body, "application/json")
