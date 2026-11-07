"""Race-day forecast from Open-Meteo (free, no key, up to 16 days ahead)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import requests

_URL = "https://api.open-meteo.com/v1/forecast"


def race_forecast(lat: float, lon: float, start: datetime) -> dict | None:
    """Rain chance (0-1) and air temperature over the two hours from the race start."""
    if start - datetime.now(timezone.utc) > timedelta(days=15):
        return None
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "precipitation_probability,temperature_2m",
        "start_date": start.date().isoformat(),
        "end_date": (start + timedelta(hours=3)).date().isoformat(),
        "timezone": "UTC",
    }
    try:
        resp = requests.get(_URL, params=params, timeout=20)
        resp.raise_for_status()
        hourly = resp.json()["hourly"]
    except (requests.RequestException, KeyError, ValueError):
        return None

    window = []
    for i, stamp in enumerate(hourly["time"]):
        t = datetime.fromisoformat(stamp).replace(tzinfo=timezone.utc)
        if start - timedelta(minutes=59) <= t <= start + timedelta(hours=2):
            window.append(i)
    if not window:
        return None
    rain = [hourly["precipitation_probability"][i] for i in window if hourly["precipitation_probability"][i] is not None]
    temp = [hourly["temperature_2m"][i] for i in window if hourly["temperature_2m"][i] is not None]
    return {
        "rain_prob": max(rain) / 100 if rain else None,
        "air_temp_c": round(sum(temp) / len(temp), 1) if temp else None,
    }
