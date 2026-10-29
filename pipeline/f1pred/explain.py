"""Turns per-feature model contributions into the short "why" shown when a driver is tapped."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .publish import team_name


def _ordinal(n: float) -> str:
    n = int(round(n))
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _ok(v) -> bool:
    return v is not None and not (isinstance(v, float) and math.isnan(v))


# Each phrase gets the driver's row and returns text, or None when the value is missing.
PHRASES = {
    "grid": lambda r: ("Starts from the pit lane" if r.get("pitlane_start") == 1 else f"Starts P{int(r['grid'])}") if _ok(r.get("grid")) else None,
    "quali_pos": lambda r: f"Qualified P{int(r['quali_pos'])}" if _ok(r.get("quali_pos")) else None,
    "quali_gap_pct": lambda r: ("Took pole position" if r["quali_gap_pct"] < 1e-6 else f"{r['quali_gap_pct']:.2f}% off pole in qualifying") if _ok(r.get("quali_gap_pct")) else None,
    "grid_penalty": lambda r: f"Grid penalty of {int(r['grid_penalty'])} places" if _ok(r.get("grid_penalty")) and r["grid_penalty"] > 0 else None,
    "pitlane_start": lambda r: "Starts from the pit lane" if r.get("pitlane_start") == 1 else None,
    "fp_longrun_gap_pct": lambda r: ("Fastest race pace in practice" if r.get("fp_longrun_rank") == 1 else f"{_ordinal(r['fp_longrun_rank'])}-best race pace in practice") if _ok(r.get("fp_longrun_rank")) else None,
    "fp_longrun_rank": lambda r: None,  # covered by fp_longrun_gap_pct
    "fp_best_gap_pct": lambda r: ("Fastest single lap in practice" if r["fp_best_gap_pct"] < 1e-6 else f"{r['fp_best_gap_pct']:.2f}% off the fastest practice lap") if _ok(r.get("fp_best_gap_pct")) else None,
    "driver_form_ewm": lambda r: f"Averaging P{r['driver_form_ewm']:.1f} in recent races" if _ok(r.get("driver_form_ewm")) else None,
    "driver_quali_ewm": lambda r: f"Qualifying around P{r['driver_quali_ewm']:.1f} lately" if _ok(r.get("driver_quali_ewm")) else None,
    "driver_last_finish": lambda r: f"Finished P{int(r['driver_last_finish'])} last time out" if _ok(r.get("driver_last_finish")) else None,
    "driver_season_avg": lambda r: f"Season average finish of P{r['driver_season_avg']:.1f}" if _ok(r.get("driver_season_avg")) else None,
    "driver_circuit_avg": lambda r: f"Averages P{r['driver_circuit_avg']:.1f} at this track over {int(r['driver_circuit_starts'])} starts" if _ok(r.get("driver_circuit_avg")) and r.get("driver_circuit_starts", 0) >= 1 else None,
    "driver_circuit_starts": lambda r: "First race at this track" if r.get("driver_circuit_starts") == 0 else None,
    "teammate_delta_ewm": lambda r: (f"Beating their teammate by {abs(r['teammate_delta_ewm']):.1f} places on average" if r["teammate_delta_ewm"] < 0 else f"Trailing their teammate by {r['teammate_delta_ewm']:.1f} places on average") if _ok(r.get("teammate_delta_ewm")) else None,
    "driver_champ_rank": lambda r: f"{_ordinal(r['driver_champ_rank'])} in the championship" if _ok(r.get("driver_champ_rank")) else None,
    "driver_points_share": lambda r: ("Leads the championship" if r["driver_points_share"] >= 0.999 else f"Has {r['driver_points_share'] * 100:.0f}% of the championship leader's points") if _ok(r.get("driver_points_share")) else None,
    "driver_win_ewm": lambda r: "Has been winning races recently" if _ok(r.get("driver_win_ewm")) and r["driver_win_ewm"] >= 0.25 else ("No recent wins" if _ok(r.get("driver_win_ewm")) else None),
    "driver_podium_ewm": lambda r: "Regular podium finisher lately" if _ok(r.get("driver_podium_ewm")) and r["driver_podium_ewm"] >= 0.4 else ("Few podiums lately" if _ok(r.get("driver_podium_ewm")) else None),
    "team_form_ewm": lambda r: f"{team_name(r['constructor_id'], r['constructor_name'])} cars averaging P{r['team_form_ewm']:.1f} recently" if _ok(r.get("team_form_ewm")) else None,
    "team_quali_ewm": lambda r: f"{team_name(r['constructor_id'], r['constructor_name'])} qualifying around P{r['team_quali_ewm']:.1f} lately" if _ok(r.get("team_quali_ewm")) else None,
    "team_points_share": lambda r: (f"{team_name(r['constructor_id'], r['constructor_name'])} lead the constructors' standings" if r["team_points_share"] >= 0.999 else f"{team_name(r['constructor_id'], r['constructor_name'])} have {r['team_points_share'] * 100:.0f}% of the leading team's points") if _ok(r.get("team_points_share")) else None,
    "driver_dnf_rate": lambda r: f"{round(r['driver_dnf_rate'] * 10)} retirements in the last 10 races" if _ok(r.get("driver_dnf_rate")) else None,
    "team_dnf_rate": lambda r: f"Team retirement rate of {r['team_dnf_rate'] * 100:.0f}% recently" if _ok(r.get("team_dnf_rate")) else None,
    "career_starts": lambda r: "Rookie with few starts" if _ok(r.get("career_starts")) and r["career_starts"] < 15 else f"Experienced, {int(r['career_starts'])} starts" if _ok(r.get("career_starts")) else None,
    "rain": lambda r: (f"{r['rain'] * 100:.0f}% chance of rain" if r["rain"] >= 0.3 else None) if _ok(r.get("rain")) else None,
    "overtaking": lambda r: "Hard track to overtake on" if r.get("overtaking", 0) >= 4 else None,
    "street": lambda r: "Street circuit" if r.get("street") == 1 else None,
    "season_races_so_far": lambda r: None,
}


def explain(race: pd.DataFrame, features: list[str], contributions: np.ndarray, top: int = 3) -> list[dict]:
    """For each driver: the factors pushing them up or down relative to the rest of the field,
    and a one-sentence summary built from the strongest positive ones."""
    relative = contributions - contributions.mean(axis=0, keepdims=True)
    out = []
    for i, (_, row) in enumerate(race.iterrows()):
        r = row.to_dict()
        factors = []
        for j in np.argsort(-np.abs(relative[i])):
            text = PHRASES.get(features[j], lambda _r: None)(r)
            if text and text not in {f["text"] for f in factors}:
                factors.append({"feature": features[j], "text": text, "impact": round(float(relative[i, j]), 4)})
            if len(factors) >= 5:
                break
        positives = [f["text"] for f in factors if f["impact"] > 0][:top]
        negatives = [f["text"] for f in factors if f["impact"] < 0][:2]
        if positives:
            summary = _sentence(positives)
            if negatives:
                summary += f" Held back by: {_lower_first(negatives[0])}."
        elif negatives:
            summary = "Up against it: " + _lower_first(_sentence(negatives))
        else:
            summary = "No standout factors either way."
        out.append({"factors": factors, "summary": summary})
    return out


_COMMON_STARTS = {
    "Starts", "Qualified", "Took", "Fastest", "Averaging", "Averages", "Beating", "Trailing", "Finished",
    "Season", "Grid", "Has", "Leads", "Regular", "Few", "No", "Hard", "Street", "Rookie", "Experienced", "First", "Team", "Qualifying",
}


def _lower_first(text: str) -> str:
    """Lowercase the first letter for use mid-sentence, unless it starts with a name."""
    return text[0].lower() + text[1:] if text.split(" ", 1)[0] in _COMMON_STARTS else text


def _sentence(parts: list[str]) -> str:
    parts = [parts[0]] + [_lower_first(p) for p in parts[1:]]
    # "X lately, Y lately and Z lately" reads badly: keep the time word only on the last part that has it.
    for word in (" lately", " recently"):
        has = [i for i, p in enumerate(parts) if p.endswith(word)]
        for i in has[:-1]:
            parts[i] = parts[i][: -len(word)]
    if len(parts) == 1:
        return parts[0] + "."
    return ", ".join(parts[:-1]) + " and " + parts[-1] + "."
