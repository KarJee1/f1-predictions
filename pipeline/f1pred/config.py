"""Runtime settings, read from environment variables so the same code runs locally and on Cloud Run."""

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Settings:
    # Where outputs and artifacts go. "gs://bucket/prefix" for Cloud Storage, otherwise a local directory.
    store_uri: str = field(default_factory=lambda: _env("F1_STORE", "./.store"))
    # Local scratch cache for raw API responses and FastF1 downloads.
    cache_dir: Path = field(default_factory=lambda: Path(_env("F1_CACHE", "./.cache")))
    jolpica_base: str = field(default_factory=lambda: _env("JOLPICA_BASE", "https://api.jolpi.ca/ergast/f1"))
    # First season used for training. FastF1 timing data starts in 2018.
    first_season: int = field(default_factory=lambda: int(_env("F1_FIRST_SEASON", "2016")))
    # Read-only starting data baked into the container image (see pipeline/seed).
    seed_dir: Path | None = field(default_factory=lambda: Path(os.environ["F1_SEED"]) if os.environ.get("F1_SEED") else None)
    # Turn off to build history from results only (fast, but no practice pace or rain).
    use_timing: bool = field(default_factory=lambda: _env("F1_TIMING", "1") == "1")
    n_simulations: int = field(default_factory=lambda: int(_env("F1_SIMULATIONS", "20000")))
    # Seasons with a big regulation change; older data is down-weighted more across these.
    regulation_resets: tuple[int, ...] = (2017, 2022, 2026)


settings = Settings()

# 2026 points for a Grand Prix (no fastest-lap point since 2025).
RACE_POINTS = [25, 18, 15, 12, 10, 8, 6, 4, 2, 1]
