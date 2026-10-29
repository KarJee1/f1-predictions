"""API for the app. Serves the JSON documents the prediction job writes to Cloud Storage, with a short
in-memory cache so most requests never touch the bucket, plus accounts and friend groups (social.py)."""

import json
import os
import re
import time
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import HTMLResponse

from social import Auth, build_router

CACHE_SECONDS = int(os.environ.get("CACHE_SECONDS", "60"))
_SAFE_PATH = re.compile(r"^[a-z0-9_\-/]+\.json$")
PRIVACY_HTML = (Path(__file__).parent / "privacy.html").read_text()


def gcs_fetcher(bucket_name: str) -> Callable[[str], bytes | None]:
    from google.cloud import storage

    bucket = storage.Client().bucket(bucket_name)
    cache: dict[str, tuple[float, bytes | None]] = {}

    def fetch(key: str) -> bytes | None:
        hit = cache.get(key)
        if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
            return hit[1]
        blob = bucket.blob(key)
        body = blob.download_as_bytes() if blob.exists() else None
        cache[key] = (time.monotonic(), body)
        return body

    return fetch


def create_app(fetch: Callable[[str], bytes | None], db, auth: Auth, **router_kwargs) -> FastAPI:
    app = FastAPI(title="F1 Predictions API", docs_url=None, redoc_url=None)

    def fetch_json(key: str):
        body = fetch(key)
        return json.loads(body) if body else None

    @app.get("/healthz")
    def health() -> dict:
        return {"ok": True}

    @app.get("/privacy", response_class=HTMLResponse)
    def privacy() -> str:
        return PRIVACY_HTML

    @app.get("/v1/{path:path}")
    def document(path: str) -> Response:
        if not _SAFE_PATH.match(path) or ".." in path:
            raise HTTPException(404)
        body = fetch(f"v1/{path}")
        if body is None:
            raise HTTPException(404)
        return Response(body, media_type="application/json", headers={"Cache-Control": f"public, max-age={CACHE_SECONDS}"})

    app.include_router(build_router(db, fetch_json, auth, **router_kwargs))
    return app


def _production_app() -> FastAPI:
    from db import FirestoreDB

    auth = Auth(os.environ.get("SESSION_SECRET"), os.environ.get("APPLE_BUNDLE_ID"))
    db = FirestoreDB() if auth.enabled else None
    return create_app(gcs_fetcher(os.environ["F1_BUCKET"]), db, auth)


app = _production_app() if "F1_BUCKET" in os.environ else None
