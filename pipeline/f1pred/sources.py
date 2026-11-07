"""Picks the timing data source: OpenF1 by default, FastF1 when F1_TIMING_SOURCE=fastf1
(FastF1 needs an F1 TV account for F1's live timing archive)."""

import os

if os.environ.get("F1_TIMING_SOURCE", "openf1") == "fastf1":
    from . import timing
else:
    from . import openf1 as timing

__all__ = ["timing"]
