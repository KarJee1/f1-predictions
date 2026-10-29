"""Practice pace and race weather from F1 live timing, via FastF1 (data from 2018 on)."""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from .config import settings

log = logging.getLogger(__name__)

_PRACTICE = ("FP1", "FP2", "FP3")
_ff1 = None


def _fastf1():
    global _ff1
    if _ff1 is None:
        import fastf1

        cache = settings.cache_dir / "fastf1"
        cache.mkdir(parents=True, exist_ok=True)
        fastf1.Cache.enable_cache(str(cache))  # still supported; `configure` is its replacement
        fastf1.set_log_level("WARNING")
        _ff1 = fastf1
    return _ff1


def _load(season: int, rnd: int, name: str, laps: bool):
    try:
        session = _fastf1().get_session(season, rnd, name)
        session.load(laps=laps, telemetry=False, weather=True, messages=False)
        return session
    except Exception as exc:  # session missing (sprint weekend) or not published yet
        log.info("No %s for %s round %s: %s", name, season, rnd, exc)
        return None


def _get(session, attr: str):
    """A loaded session attribute, or None when that part of the data failed to load."""
    if session is None:
        return None
    try:
        value = getattr(session, attr)
    except Exception:
        return None
    return None if value is None or getattr(value, "empty", False) else value


def _long_run_pace(laps: pd.DataFrame) -> pd.Series:
    """Mean lap time of each driver's best long run (5+ clean green-flag laps in one stint)."""
    clean = laps.pick_wo_box().pick_track_status("1")
    clean = clean[clean["LapTime"].notna()].copy()
    clean["t"] = clean["LapTime"].dt.total_seconds()
    pace = {}
    for (driver, _stint), stint in clean.groupby(["Driver", "Stint"]):
        if len(stint) < 5:
            continue
        stint = stint[stint["t"] < stint["t"].median() * 1.07]
        if len(stint) >= 5:
            pace[driver] = min(pace.get(driver, np.inf), stint["t"].mean())
    return pd.Series(pace, dtype=float)


def practice_features(season: int, rnd: int) -> pd.DataFrame:
    """Per-driver practice pace for one weekend, indexed by three-letter driver code.

    fp_best_gap_pct: best single lap vs the fastest lap of that session, best across sessions.
    fp_longrun_gap_pct: long-run pace vs the best long run, from the latest session that had long runs.
    """
    best_gaps: list[pd.Series] = []
    long_run: pd.Series | None = None
    for name in _PRACTICE:
        laps = _get(_load(season, rnd, name, laps=True), "laps")
        if laps is None:
            continue
        best = laps.pick_wo_box().groupby("Driver")["LapTime"].min().dt.total_seconds().dropna()
        if not best.empty:
            best_gaps.append((best / best.min() - 1) * 100)
        lr = _long_run_pace(laps)
        if len(lr) >= 5:
            long_run = (lr / lr.min() - 1) * 100

    if not best_gaps and long_run is None:
        return pd.DataFrame(columns=["fp_best_gap_pct", "fp_longrun_gap_pct"])
    out = pd.DataFrame(index=sorted(set().union(*(s.index for s in best_gaps), long_run.index if long_run is not None else [])))
    out["fp_best_gap_pct"] = pd.concat(best_gaps, axis=1).min(axis=1) if best_gaps else np.nan
    out["fp_longrun_gap_pct"] = long_run if long_run is not None else np.nan
    return out


def race_rain(season: int, rnd: int) -> float | None:
    """1.0 if rain was recorded at any point in the race, 0.0 if dry, None if unknown."""
    weather = _get(_load(season, rnd, "R", laps=False), "weather_data")
    if weather is None:
        return None
    return float(weather["Rainfall"].astype(bool).any())


def quali_results(season: int, rnd: int) -> pd.DataFrame:
    """Qualifying order from live timing, used when Jolpica hasn't published it yet."""
    res = _get(_load(season, rnd, "Q", laps=False), "results")
    if res is None:
        return pd.DataFrame()
    times = res[["Q1", "Q2", "Q3"]].apply(lambda col: col.dt.total_seconds())
    return pd.DataFrame(
        {
            "code": res["Abbreviation"].values,
            "number": res["DriverNumber"].astype(str).values,
            "quali_pos": pd.to_numeric(res["Position"], errors="coerce").values,
            "quali_best": times.min(axis=1).values,
        }
    )


def session_entries(season: int, rnd: int, name: str) -> pd.DataFrame:
    """The drivers taking part in a session, with team name and official team color."""
    res = _get(_load(season, rnd, name, laps=False), "results")
    if res is None or res["Abbreviation"].isna().all():
        return pd.DataFrame()
    return pd.DataFrame(
        {
            "code": res["Abbreviation"].values,
            "number": res["DriverNumber"].astype(str).values,
            "first_name": res["FirstName"].values,
            "last_name": res["LastName"].values,
            "team_name": res["TeamName"].values,
            "team_color": ["#" + c if isinstance(c, str) and c and not c.startswith("#") else c for c in res["TeamColor"].values],
        }
    )
