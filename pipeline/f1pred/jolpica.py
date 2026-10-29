"""Client for the Jolpica F1 API (the Ergast-compatible successor to Ergast).

Responses are cached on disk. Finished seasons are cached forever; the current season expires
after `ttl` seconds so new results show up. Jolpica allows a few requests per second and about
500 per hour, so the client sleeps between uncached calls.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path
from typing import Any

import requests

from .config import settings

_PAGE = 100
_MIN_INTERVAL = 0.3


class Jolpica:
    def __init__(self, base: str | None = None, cache_dir: Path | None = None, ttl: int = 1800):
        self.base = (base or settings.jolpica_base).rstrip("/")
        self.cache_dir = (cache_dir or settings.cache_dir) / "jolpica"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl
        self._last_call = 0.0
        self._session = requests.Session()

    # -- low level ---------------------------------------------------------------------------

    def _cache_path(self, url: str) -> Path:
        return self.cache_dir / (sha1(url.encode()).hexdigest() + ".json")

    def _get(self, path: str, params: dict[str, Any], permanent: bool) -> dict:
        url = f"{self.base}/{path}.json?" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        cached = self._cache_path(url)
        if cached.exists() and (permanent or time.time() - cached.stat().st_mtime < self.ttl):
            return json.loads(cached.read_text())

        for attempt in range(5):
            wait = _MIN_INTERVAL - (time.time() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.time()
            resp = self._session.get(url, timeout=30)
            if resp.status_code == 429:
                time.sleep(int(resp.headers.get("Retry-After", 2 ** (attempt + 2))))
                continue
            resp.raise_for_status()
            data = resp.json()
            cached.write_text(json.dumps(data))
            return data
        raise RuntimeError(f"Jolpica kept rate limiting {url}")

    def _races(self, path: str, season: int) -> list[dict]:
        """Fetch every page of a race-table endpoint and merge pages that split a race."""
        permanent = season < datetime.now(timezone.utc).year
        races: dict[int, dict] = {}
        offset = 0
        while True:
            data = self._get(path, {"limit": _PAGE, "offset": offset}, permanent)["MRData"]
            for race in data["RaceTable"]["Races"]:
                rnd = int(race["round"])
                if rnd in races:
                    for key, value in race.items():
                        if isinstance(value, list):
                            races[rnd].setdefault(key, []).extend(value)
                else:
                    races[rnd] = race
            offset += _PAGE
            if offset >= int(data["total"]):
                break
        return [races[r] for r in sorted(races)]

    # -- endpoints ---------------------------------------------------------------------------

    def schedule(self, season: int) -> list[dict]:
        return self._races(f"{season}", season)

    def results(self, season: int) -> list[dict]:
        return self._races(f"{season}/results", season)

    def qualifying(self, season: int) -> list[dict]:
        return self._races(f"{season}/qualifying", season)

    def round_qualifying(self, season: int, rnd: int) -> list[dict]:
        races = self._get(f"{season}/{rnd}/qualifying", {"limit": _PAGE}, False)["MRData"]["RaceTable"]["Races"]
        return races[0]["QualifyingResults"] if races else []

    def round_results(self, season: int, rnd: int) -> list[dict]:
        races = self._get(f"{season}/{rnd}/results", {"limit": _PAGE}, False)["MRData"]["RaceTable"]["Races"]
        return races[0]["Results"] if races else []

    def driver_standings(self, season: int) -> list[dict]:
        lists = self._get(f"{season}/driverstandings", {"limit": _PAGE}, False)["MRData"]["StandingsTable"]["StandingsLists"]
        return lists[0]["DriverStandings"] if lists else []

    def constructor_standings(self, season: int) -> list[dict]:
        lists = self._get(f"{season}/constructorstandings", {"limit": _PAGE}, False)["MRData"]["StandingsTable"]["StandingsLists"]
        return lists[0]["ConstructorStandings"] if lists else []


def parse_lap_time(value: str | None) -> float | None:
    """'1:23.456' -> 83.456 seconds."""
    if not value:
        return None
    try:
        if ":" in value:
            minutes, seconds = value.split(":", 1)
            return int(minutes) * 60 + float(seconds)
        return float(value)
    except ValueError:
        return None


def session_start(race: dict, key: str | None = None) -> datetime | None:
    """UTC start of a session block in a schedule entry (key=None means the race itself)."""
    block = race if key is None else race.get(key)
    if not block or "date" not in block:
        return None
    clock = block.get("time", "00:00:00Z").rstrip("Z")
    return datetime.fromisoformat(f"{block['date']}T{clock}").replace(tzinfo=timezone.utc)
