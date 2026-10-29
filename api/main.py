"""Read-only API for the app. Serves the JSON documents the prediction job writes to Cloud Storage,
with a short in-memory cache so most requests never touch the bucket."""

import os
import re
import time

from fastapi import FastAPI, HTTPException, Response
from google.cloud import storage

BUCKET = os.environ["F1_BUCKET"]
CACHE_SECONDS = int(os.environ.get("CACHE_SECONDS", "60"))
_SAFE_PATH = re.compile(r"^[a-z0-9_\-/]+\.json$")

app = FastAPI(title="F1 Predictions API", docs_url=None, redoc_url=None)
_bucket = storage.Client().bucket(BUCKET)
_cache: dict[str, tuple[float, bytes | None]] = {}


def _fetch(key: str) -> bytes | None:
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]
    blob = _bucket.blob(key)
    body = blob.download_as_bytes() if blob.exists() else None
    _cache[key] = (time.monotonic(), body)
    return body


@app.get("/healthz")
def health() -> dict:
    return {"ok": True}


@app.get("/v1/{path:path}")
def document(path: str) -> Response:
    if not _SAFE_PATH.match(path) or ".." in path:
        raise HTTPException(404)
    body = _fetch(f"v1/{path}")
    if body is None:
        raise HTTPException(404)
    return Response(body, media_type="application/json", headers={"Cache-Control": f"public, max-age={CACHE_SECONDS}"})
