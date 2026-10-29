"""Builds the JSON documents the app reads. Paths are relative to the store root under `v1/`."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .config import RACE_POINTS


_TEAM_NAMES = {"rb": "Racing Bulls", "sauber": "Sauber", "audi": "Audi"}


def team_name(team_id: str | None, name: str | None) -> str | None:
    """Short display names, e.g. "Haas F1 Team" -> "Haas"."""
    if team_id in _TEAM_NAMES:
        return _TEAM_NAMES[team_id]
    return name.replace(" F1 Team", "").strip() if name else name


def _iso(value) -> str | None:
    if value is None or (isinstance(value, float) and np.isnan(value)) or pd.isna(value):
        return None
    return pd.Timestamp(value).isoformat()


def race_info(race: pd.Series) -> dict:
    return {
        "season": int(race["season"]),
        "round": int(race["round"]),
        "race_name": race["race_name"],
        "circuit_id": race["circuit_id"],
        "circuit_name": race["circuit_name"],
        "locality": race["locality"],
        "country": race["country"],
        "race_start": _iso(race["race_start"]),
        "sessions": {
            "fp1": _iso(race["fp1_start"]),
            "fp2": _iso(race["fp2_start"]),
            "fp3": _iso(race["fp3_start"]),
            "quali": _iso(race["quali_start"]),
            "sprint": _iso(race["sprint_start"]),
        },
    }


def prediction_doc(race: pd.Series, stage: str, rows: pd.DataFrame, sim: dict, explanations: list[dict],
                   model_kind: str, weather: dict | None, team_colors: dict[str, str]) -> dict:
    drivers = []
    for i, (_, r) in enumerate(rows.iterrows()):
        drivers.append(
            {
                "driver_id": r["driver_id"],
                "code": r["code"],
                "number": None if pd.isna(r["number"]) else str(r["number"]),
                "first_name": r["first_name"],
                "last_name": r["last_name"],
                "team_id": r["constructor_id"],
                "team_name": team_name(r["constructor_id"], r["constructor_name"]),
                "team_color": team_colors.get(r["constructor_id"]),
                "grid": None if pd.isna(r.get("grid")) else int(r["grid"]),
                "win_pct": round(float(sim["win"][i]) * 100, 1),
                "podium_pct": round(float(sim["podium"][i]) * 100, 1),
                "points_pct": round(float(sim["points"][i]) * 100, 1),
                "dnf_pct": round(float(sim["dnf"][i]) * 100, 1),
                "expected_position": round(float(sim["expected_position"][i]), 2),
                "expected_points": round(float(sim["expected_points"][i]), 2),
                "position_distribution": [round(float(p), 4) for p in sim["distribution"][i]],
                "summary": explanations[i]["summary"],
                "factors": explanations[i]["factors"],
            }
        )
    # The list order is the predicted finishing order: by win chance, then podium chance,
    # then expected position for the drivers with no realistic shot at winning.
    drivers.sort(key=lambda d: (-d["win_pct"], -d["podium_pct"], d["expected_position"]))
    for pos, d in enumerate(drivers, start=1):
        d["predicted_position"] = pos
    return {
        "race": race_info(race),
        "stage": stage,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": model_kind,
        "weather": weather,
        "drivers": drivers,
    }


def results_doc(race: pd.Series, results: list[dict]) -> dict:
    return {
        "race": race_info(race),
        "results": [
            {
                "position": int(r["position"]),
                "classified": r["positionText"].isdigit(),
                "driver_id": r["Driver"]["driverId"],
                "code": r["Driver"].get("code"),
                "first_name": r["Driver"]["givenName"],
                "last_name": r["Driver"]["familyName"],
                "team_id": r["Constructor"]["constructorId"],
                "team_name": team_name(r["Constructor"]["constructorId"], r["Constructor"]["name"]),
                "grid": int(r["grid"]) if r.get("grid") else None,
                "status": r["status"],
                "points": float(r["points"]),
            }
            for r in sorted(results, key=lambda r: int(r["position"]))
        ],
    }


def standings_doc(driver_standings: list[dict], constructor_standings: list[dict], prediction: dict | None,
                  team_colors: dict[str, str]) -> dict:
    """Current standings, plus where everyone would be if the predicted finishing order comes true."""
    gained: dict[str, float] = {}
    team_gained: dict[str, float] = {}
    if prediction:
        for d in prediction["drivers"]:
            pts = RACE_POINTS[d["predicted_position"] - 1] if d["predicted_position"] <= len(RACE_POINTS) else 0
            gained[d["driver_id"]] = pts
            team_gained[d["team_id"]] = team_gained.get(d["team_id"], 0) + pts

    drivers = []
    for s in driver_standings:
        drv = s["Driver"]
        con = s["Constructors"][-1] if s.get("Constructors") else {}
        drivers.append(
            {
                "driver_id": drv["driverId"],
                "code": drv.get("code"),
                "first_name": drv["givenName"],
                "last_name": drv["familyName"],
                "team_id": con.get("constructorId"),
                "team_name": team_name(con.get("constructorId"), con.get("name")),
                "team_color": team_colors.get(con.get("constructorId", "")),
                "position": int(s.get("position") or len(drivers) + 1),
                "points": float(s["points"]),
                "wins": int(s["wins"]),
            }
        )
    # Prefer the team from the latest entry list: a driver who changed teams mid-season is listed
    # under every team they drove for in the standings.
    current = {d["driver_id"]: d for d in prediction["drivers"]} if prediction else {}
    for d in drivers:
        if d["driver_id"] in current:
            e = current[d["driver_id"]]
            d.update(team_id=e["team_id"], team_name=e.get("team_name", d["team_name"]), team_color=e.get("team_color", d["team_color"]))
    known = {d["driver_id"] for d in drivers}
    if prediction:  # drivers who haven't scored a championship entry yet (e.g. a mid-season replacement)
        for d in prediction["drivers"]:
            if d["driver_id"] not in known:
                drivers.append({k: d[k] for k in ("driver_id", "code", "first_name", "last_name", "team_id", "team_name", "team_color")}
                               | {"position": len(drivers) + 1, "points": 0.0, "wins": 0})
    _project(drivers, gained, "driver_id")

    teams = []
    for s in constructor_standings:
        con = s["Constructor"]
        teams.append(
            {
                "team_id": con["constructorId"],
                "team_name": team_name(con["constructorId"], con["name"]),
                "team_color": team_colors.get(con["constructorId"]),
                "position": int(s.get("position") or len(teams) + 1),
                "points": float(s["points"]),
                "wins": int(s["wins"]),
            }
        )
    _project(teams, team_gained, "team_id")
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "after_race": prediction["race"] if prediction else None,
        "drivers": drivers,
        "constructors": teams,
    }


def _project(entries: list[dict], gained: dict[str, float], key: str) -> None:
    for e in entries:
        e["predicted_points"] = e["points"] + gained.get(e[key], 0)
    # Ties keep the current order, a reasonable stand-in for the countback on wins.
    ranked = sorted(entries, key=lambda e: (-e["predicted_points"], e["position"]))
    for pos, e in enumerate(ranked, start=1):
        e["predicted_position"] = pos
        e["position_change"] = e["position"] - pos
