"""Command line entry point.

  f1pred backfill            download all history (first run takes a while: FastF1 timing is large)
  f1pred train               backtest model types, pick the best per stage, save models
  f1pred backtest 2024 2025  print backtest metrics only
  f1pred backfill-accuracy 2026   accuracy history for races before the app went live
  f1pred run                 one scheduled tick: score, predict, standings, news (what Cloud Run runs)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timedelta, timezone

from .evaluate import backtest, summarize
from .features import build_features
from .pipeline import Pipeline


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="f1pred")
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backfill")
    b.add_argument("--full", action="store_true", help="rebuild every season instead of only missing ones")
    sub.add_parser("train")
    bt = sub.add_parser("backtest")
    bt.add_argument("seasons", type=int, nargs="+")
    ba = sub.add_parser("backfill-accuracy")
    ba.add_argument("season", type=int)
    r = sub.add_parser("run")
    r.add_argument("--force", action="store_true", help="re-predict even if nothing changed")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    pipe = Pipeline()
    if args.cmd == "backfill":
        history = pipe.refresh_history(full=args.full)
        print(f"{len(history)} rows, seasons {history['season'].min()}-{history['season'].max()}")
    elif args.cmd == "train":
        print(json.dumps(pipe.train(), indent=2, default=str))
    elif args.cmd == "backtest":
        print(summarize(backtest(build_features(pipe.history()), args.seasons)).to_string())
    elif args.cmd == "backfill-accuracy":
        print(json.dumps(pipe.backfill_accuracy(args.season), indent=2))
    elif args.cmd == "run":
        _locked_run(pipe, force=args.force)


LOCK_KEY = "data/run-lock.json"
LOCK_TTL = timedelta(hours=2, minutes=30)  # longer than the job's task timeout, so a crashed run can't block forever


def _locked_run(pipe: Pipeline, force: bool) -> None:
    """Run one tick unless another run is still going (the hourly schedule can overlap a long first run)."""
    now = datetime.now(timezone.utc)
    lock = pipe.store.read_json(LOCK_KEY) or {}
    started = lock.get("started_at")
    if started and now - datetime.fromisoformat(started) < LOCK_TTL and not force:
        print(json.dumps({"skipped": "another run is in progress", "since": started}))
        return
    pipe.store.write_json(LOCK_KEY, {"started_at": now.isoformat(), "execution": os.environ.get("CLOUD_RUN_EXECUTION")})
    try:
        print(json.dumps(pipe.run(force=force), indent=2))
    finally:
        pipe.store.write_json(LOCK_KEY, {"started_at": None})


if __name__ == "__main__":
    main()
