"""Builds the historical race table: one row per driver per Grand Prix, with results,
qualifying, practice pace and rain. Sprint races are not included.
"""

from __future__ import annotations

import io
import logging

import numpy as np
import pandas as pd

from .sources import timing
from .jolpica import Jolpica, parse_lap_time, session_start
from .storage import Store

log = logging.getLogger(__name__)

# Constructor renames, so team form carries over (e.g. Sauber became Audi in 2026).
TEAM_LINEAGE = {
    "force_india": "aston_martin",
    "racing_point": "aston_martin",
    "toro_rosso": "rb",
    "alphatauri": "rb",
    "renault": "alpine",
    "lotus_f1": "alpine",
    "alfa": "sauber",
    "audi": "sauber",
    "marussia": "manor",
}


def team_key(constructor_id: str) -> str:
    return TEAM_LINEAGE.get(constructor_id, constructor_id)


def _race_rows(race: dict) -> list[dict]:
    rows = []
    for r in race.get("Results", []):
        drv, con = r["Driver"], r["Constructor"]
        rows.append(
            {
                "season": int(race["season"]),
                "round": int(race["round"]),
                "race_name": race["raceName"],
                "circuit_id": race["Circuit"]["circuitId"],
                "date": race["date"],
                "driver_id": drv["driverId"],
                "code": drv.get("code") or drv["driverId"][:3].upper(),
                "number": r.get("number") or drv.get("permanentNumber"),
                "first_name": drv["givenName"],
                "last_name": drv["familyName"],
                "constructor_id": con["constructorId"],
                "constructor_name": con["name"],
                "grid": int(r["grid"]) if r.get("grid") not in (None, "") else np.nan,
                "position": int(r["position"]),
                "classified": r["positionText"].isdigit(),
                "status": r["status"],
                "points": float(r["points"]),
            }
        )
    return rows


def _quali_rows(race: dict) -> list[dict]:
    rows = []
    for q in race.get("QualifyingResults", []):
        times = [parse_lap_time(q.get(k)) for k in ("Q1", "Q2", "Q3")]
        times = [t for t in times if t]
        rows.append(
            {
                "season": int(race["season"]),
                "round": int(race["round"]),
                "driver_id": q["Driver"]["driverId"],
                "quali_pos": int(q["position"]),
                "quali_best": min(times) if times else np.nan,
            }
        )
    return rows


def _timing_for(season: int, rnd: int) -> tuple[pd.DataFrame, float | None]:
    """Practice pace + race rain for one finished race. Slow to fetch, so it's cached in the store
    (Cloud Storage in production), where it survives between job runs."""
    store = Store()
    key = f"cache/timing/{season}_{rnd:02d}"
    blob, meta = store.read_bytes(f"{key}.parquet"), store.read_json(f"{key}.json")
    if blob is not None and meta is not None:
        return pd.read_parquet(io.BytesIO(blob)), meta["rain"]
    try:
        fp = timing.practice_features(season, rnd)
        rain = timing.race_rain(season, rnd)
    except Exception:  # timing data is a bonus; never let it stop the pipeline
        log.exception("Timing data failed for %s round %s", season, rnd)
        return pd.DataFrame(columns=["fp_best_gap_pct", "fp_longrun_gap_pct"]), None
    if fp.empty and rain is None:
        return fp, rain  # nothing loaded (often a network problem); don't cache, try again next time
    buf = io.BytesIO()
    fp.to_parquet(buf)
    store.write_bytes(f"{key}.parquet", buf.getvalue())
    store.write_json(f"{key}.json", {"rain": rain})
    return fp, rain


def build_history(client: Jolpica, seasons: list[int], with_timing: bool = True) -> pd.DataFrame:
    frames = []
    for season in seasons:
        log.info("Loading season %s", season)
        results = pd.DataFrame([row for race in client.results(season) for row in _race_rows(race)])
        if results.empty:
            continue
        quali = pd.DataFrame([row for race in client.qualifying(season) for row in _quali_rows(race)])
        if not quali.empty:
            results = results.merge(quali, on=["season", "round", "driver_id"], how="left")
        else:
            results["quali_pos"], results["quali_best"] = np.nan, np.nan

        results["fp_best_gap_pct"], results["fp_longrun_gap_pct"], results["rain"] = np.nan, np.nan, np.nan
        if with_timing and season >= 2018:
            for rnd in sorted(results["round"].unique()):
                fp, rain = _timing_for(season, int(rnd))
                mask = results["round"] == rnd
                if not fp.empty:
                    results.loc[mask, "fp_best_gap_pct"] = results.loc[mask, "code"].map(fp["fp_best_gap_pct"])
                    results.loc[mask, "fp_longrun_gap_pct"] = results.loc[mask, "code"].map(fp["fp_longrun_gap_pct"])
                if rain is not None:
                    results.loc[mask, "rain"] = rain
        frames.append(results)

    history = pd.concat(frames, ignore_index=True)
    return history.sort_values(["season", "round", "position"]).reset_index(drop=True)


def schedule_frame(client: Jolpica, season: int) -> pd.DataFrame:
    rows = []
    for race in client.schedule(season):
        loc = race["Circuit"]["Location"]
        rows.append(
            {
                "season": season,
                "round": int(race["round"]),
                "race_name": race["raceName"],
                "circuit_id": race["Circuit"]["circuitId"],
                "circuit_name": race["Circuit"]["circuitName"],
                "locality": loc.get("locality"),
                "country": loc.get("country"),
                "lat": float(loc["lat"]),
                "lon": float(loc["long"]),
                "date": race["date"],
                "race_start": session_start(race),
                "fp1_start": session_start(race, "FirstPractice"),
                "fp2_start": session_start(race, "SecondPractice"),
                "fp3_start": session_start(race, "ThirdPractice"),
                "quali_start": session_start(race, "Qualifying"),
                "sprint_quali_start": session_start(race, "SprintQualifying") or session_start(race, "SprintShootout"),
                "sprint_start": session_start(race, "Sprint"),
            }
        )
    return pd.DataFrame(rows)
