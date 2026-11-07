"""Scores friend-group picks after each race (the API in api/social.py stores them in Firestore).

Each pick gets its score written onto it, and the points are added to the user's season total, which is
what group leaderboards show. A pick that already has a score is skipped, so running this twice is safe.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

POINTS_PER_DRIVER = 5  # same rule as the app's Predict tab (app/src/picks.ts)


def score_order(order: list[str], results: list[dict]) -> dict:
    """Up to 5 points per driver: 5 for the exact position, one less for each place off."""
    actual = {r["driver_id"]: int(r["position"]) for r in results}
    score = exact = counted = 0
    for i, driver in enumerate(order):
        pos = actual.get(driver)
        if pos is None:
            continue
        counted += 1
        off = abs(i + 1 - pos)
        exact += off == 0
        score += max(0, POINTS_PER_DRIVER - off)
    return {"score": score, "max": counted * POINTS_PER_DRIVER, "exact": exact}


def score_race(season: int, rnd: int, results: list[dict], client=None) -> int:
    """Score every unscored pick for one race. Returns how many picks were scored."""
    from google.cloud import firestore
    from google.cloud.firestore_v1.base_query import FieldFilter

    client = client or firestore.Client()
    picks = (
        client.collection("picks")
        .where(filter=FieldFilter("season", "==", season))
        .where(filter=FieldFilter("round", "==", rnd))
        .stream()
    )
    pending = [p for p in picks if "score" not in (p.to_dict() or {})]
    for start in range(0, len(pending), 200):  # a batch holds 500 writes; each pick takes two
        batch = client.batch()
        for snap in pending[start : start + 200]:
            pick = snap.to_dict()
            s = score_order(pick["order"], results)
            batch.update(snap.reference, s)
            totals = {"points": firestore.Increment(s["score"]), "races": firestore.Increment(1), "exact": firestore.Increment(s["exact"])}
            batch.set(client.collection("users").document(pick["uid"]), {"totals": {str(season): totals}}, merge=True)
        batch.commit()
    log.info("Scored %d group picks for %s round %s", len(pending), season, rnd)
    return len(pending)
