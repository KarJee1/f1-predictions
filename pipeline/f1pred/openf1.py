"""Practice pace, entry lists, qualifying and race weather from the OpenF1 API (free for
historical data, from 2023 on). F1's own timing feed now needs an F1 TV login, so this is the
default timing source; FastF1 (timing.py) is used only when OPENF1 is turned off.

Sessions are matched to a Jolpica round by date: a meeting whose race falls on the round's date.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timedelta, timezone
from hashlib import sha1

import numpy as np
import pandas as pd
import requests

from .config import settings

log = logging.getLogger(__name__)

BASE = "https://api.openf1.org/v1"
_MIN_INTERVAL = 2.1  # the free tier allows 30 requests a minute
_last_call = 0.0
_PRACTICE = ("Practice 1", "Practice 2", "Practice 3")


def _get(endpoint: str, permanent: bool, **params) -> list[dict]:
    global _last_call
    url = f"{BASE}/{endpoint}?" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    folder = settings.cache_dir / "openf1"
    folder.mkdir(parents=True, exist_ok=True)
    cached = folder / (sha1(url.encode()).hexdigest() + ".json")
    if cached.exists() and (permanent or time.time() - cached.stat().st_mtime < 900):
        return json.loads(cached.read_text())
    for attempt in range(5):
        wait = _MIN_INTERVAL - (time.time() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.time()
        try:
            resp = requests.get(url, timeout=30)
        except requests.RequestException as exc:
            log.warning("OpenF1 %s failed: %s", url, exc)
            return []
        if resp.status_code == 429:
            time.sleep(10 * (attempt + 1))
            continue
        if resp.status_code == 404:  # OpenF1 answers 404 when a filter matches nothing
            data = []
        elif resp.ok:
            data = resp.json()
        else:
            log.warning("OpenF1 %s answered %s", url, resp.status_code)
            return []
        cached.write_text(json.dumps(data))
        return data
    return []


def _sessions(season: int) -> list[dict]:
    return _get("sessions", permanent=season < datetime.now(timezone.utc).year, year=season)


def _race_date(season: int, rnd: int) -> date | None:
    from .jolpica import Jolpica

    for race in Jolpica().schedule(season):
        if int(race["round"]) == rnd:
            return date.fromisoformat(race["date"])
    return None


def _weekend(season: int, rnd: int) -> dict[str, dict]:
    """The weekend's sessions by name, e.g. {'Practice 1': {...}, 'Qualifying': {...}, 'Race': {...}}."""
    race_day = _race_date(season, rnd)
    if race_day is None:
        return {}
    sessions = _sessions(season)
    meeting = None
    for s in sessions:
        if s.get("session_name") == "Race" and s.get("date_start", "")[:10] in {
            (race_day + timedelta(days=d)).isoformat() for d in (-1, 0, 1)
        }:
            meeting = s["meeting_key"]
    if meeting is None:
        return {}
    return {s["session_name"]: s for s in sessions if s["meeting_key"] == meeting}


def _finished(session: dict) -> bool:
    end = session.get("date_end")
    return bool(end) and datetime.fromisoformat(end) < datetime.now(timezone.utc) - timedelta(minutes=30)


def _drivers(session: dict) -> pd.DataFrame:
    rows = _get("drivers", _finished(session), session_key=session["session_key"])
    df = pd.DataFrame(rows)
    return df.drop_duplicates("driver_number") if not df.empty else df


def _codes(session: dict) -> dict[int, str]:
    d = _drivers(session)
    return dict(zip(d["driver_number"], d["name_acronym"])) if not d.empty else {}


def _laps(session: dict) -> pd.DataFrame:
    laps = pd.DataFrame(_get("laps", _finished(session), session_key=session["session_key"]))
    if laps.empty or "lap_duration" not in laps:
        return pd.DataFrame()
    stints = pd.DataFrame(_get("stints", _finished(session), session_key=session["session_key"]))
    laps["stint"] = np.nan
    laps["last_of_stint"] = False
    for _, s in stints.iterrows():
        mask = (laps["driver_number"] == s["driver_number"]) & laps["lap_number"].between(s["lap_start"], s["lap_end"])
        laps.loc[mask, "stint"] = s["stint_number"]
        laps.loc[mask & (laps["lap_number"] == s["lap_end"]), "last_of_stint"] = True
    laps["code"] = laps["driver_number"].map(_codes(session))
    return laps[laps["code"].notna()]


def _long_run_pace(laps: pd.DataFrame) -> pd.Series:
    clean = laps[laps["lap_duration"].notna() & ~laps["is_pit_out_lap"].fillna(False).astype(bool) & ~laps["last_of_stint"]]
    pace = {}
    for (code, _stint), stint in clean.groupby(["code", "stint"]):
        t = stint["lap_duration"]
        t = t[t < t.median() * 1.07]
        if len(t) >= 5:
            pace[code] = min(pace.get(code, np.inf), t.mean())
    return pd.Series(pace, dtype=float)


def practice_features(season: int, rnd: int) -> pd.DataFrame:
    """Same output as timing.practice_features: gaps in percent, indexed by driver code."""
    weekend = _weekend(season, rnd)
    best_gaps, long_run = [], None
    for name in _PRACTICE:
        session = weekend.get(name)
        if not session or not _finished(session):
            continue
        laps = _laps(session)
        if laps.empty:
            continue
        valid = laps[~laps["is_pit_out_lap"].fillna(False).astype(bool)]
        best = valid.groupby("code")["lap_duration"].min().dropna()
        if not best.empty:
            best_gaps.append((best / best.min() - 1) * 100)
        lr = _long_run_pace(laps)
        # Use the session where most drivers did race-pace runs (usually FP2), not just the latest.
        if len(lr) >= 5 and (long_run is None or len(lr) > len(long_run)):
            long_run = (lr / lr.min() - 1) * 100
    if not best_gaps and long_run is None:
        return pd.DataFrame(columns=["fp_best_gap_pct", "fp_longrun_gap_pct"])
    index = sorted(set().union(*(s.index for s in best_gaps), long_run.index if long_run is not None else []))
    out = pd.DataFrame(index=index)
    out["fp_best_gap_pct"] = pd.concat(best_gaps, axis=1).min(axis=1) if best_gaps else np.nan
    out["fp_longrun_gap_pct"] = long_run if long_run is not None else np.nan
    return out


def race_rain(season: int, rnd: int) -> float | None:
    session = _weekend(season, rnd).get("Race")
    if not session or not _finished(session):
        return None
    weather = _get("weather", True, session_key=session["session_key"])
    if not weather:
        return None
    return float(any(w.get("rainfall") for w in weather))


def quali_results(season: int, rnd: int) -> pd.DataFrame:
    session = _weekend(season, rnd).get("Qualifying")
    if not session or not _finished(session):
        return pd.DataFrame()
    laps = _laps(session)
    results = _get("session_result", True, session_key=session["session_key"])
    if not results:
        return pd.DataFrame()
    codes = _codes(session)
    best = laps.groupby("code")["lap_duration"].min() if not laps.empty else pd.Series(dtype=float)
    rows = [
        {"code": codes.get(r["driver_number"]), "number": str(r["driver_number"]), "quali_pos": r.get("position"), "quali_best": best.get(codes.get(r["driver_number"]), np.nan)}
        for r in results
    ]
    return pd.DataFrame([r for r in rows if r["code"]])


_SESSION_NAMES = {"FP1": "Practice 1", "FP2": "Practice 2", "FP3": "Practice 3", "Q": "Qualifying", "R": "Race"}


def session_entries(season: int, rnd: int, name: str) -> pd.DataFrame:
    session = _weekend(season, rnd).get(_SESSION_NAMES.get(name, name))
    if not session:
        return pd.DataFrame()
    d = _drivers(session)
    if d.empty:
        return pd.DataFrame()
    return pd.DataFrame(
        {
            "code": d["name_acronym"].values,
            "number": d["driver_number"].astype(str).values,
            "first_name": d["first_name"].values,
            "last_name": d["last_name"].values,
            "team_name": d["team_name"].values,
            "team_color": ["#" + c if isinstance(c, str) and c and not c.startswith("#") else c for c in d["team_colour"].values],
        }
    )
