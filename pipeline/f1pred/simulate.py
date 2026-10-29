"""Turns per-driver model scores into race outcome probabilities.

Each simulated race: every driver may retire (DNF) with their own probability; the rest finish
in an order drawn from a Plackett-Luce model on the scores (implemented with Gumbel noise, which
samples exactly from Plackett-Luce). Retirements fill the back of the order.
"""

from __future__ import annotations

import numpy as np

from .config import RACE_POINTS

BASE_DNF_RATE = 0.10


def dnf_probability(team_rate: np.ndarray, driver_rate: np.ndarray, base: float = BASE_DNF_RATE) -> np.ndarray:
    team = np.where(np.isnan(team_rate), base, team_rate)
    driver = np.where(np.isnan(driver_rate), base, driver_rate)
    return np.clip(0.5 * team + 0.3 * driver + 0.2 * base, 0.02, 0.35)


def simulate(scores: np.ndarray, beta: float, p_dnf: np.ndarray, n: int = 20000, seed: int = 7) -> dict[str, np.ndarray]:
    """Returns per-driver win/podium/points probability, expected position and the full position
    distribution (drivers x positions)."""
    rng = np.random.default_rng(seed)
    k = len(scores)
    utility = beta * (scores - scores.max()) + rng.gumbel(size=(n, k))
    retired = rng.random((n, k)) < p_dnf
    # Retired cars sort behind every finisher; their own order among themselves is random.
    utility = np.where(retired, -1e6 + rng.random((n, k)), utility)
    order = np.argsort(-utility, axis=1)
    positions = np.empty_like(order)
    rows = np.arange(n)[:, None]
    positions[rows, order] = np.arange(k)[None, :]

    dist = np.zeros((k, k))
    for pos in range(k):
        dist[:, pos] = (positions == pos).mean(axis=0)
    finish_positions = positions + 1
    points_table = np.array(RACE_POINTS + [0] * max(0, k - len(RACE_POINTS)), dtype=float)[:k]
    return {
        "win": dist[:, 0],
        "podium": dist[:, :3].sum(axis=1),
        "points": dist[:, : len(RACE_POINTS)].sum(axis=1),
        "dnf": retired.mean(axis=0),
        "expected_position": finish_positions.mean(axis=0),
        "expected_points": dist @ points_table,
        "distribution": dist,
    }


def plackett_luce_loglik(scores_in_finish_order: np.ndarray, beta: float) -> float:
    """Log-likelihood of an observed finishing order (finishers only) under Plackett-Luce."""
    u = beta * scores_in_finish_order
    # log-sum-exp of each suffix u[k:], computed from the back.
    suffix = np.logaddexp.accumulate(u[::-1])[::-1]
    return float((u - suffix).sum())


def fit_beta(races: list[np.ndarray]) -> float:
    """Pick the score temperature that best explains observed finishing orders."""
    grid = np.exp(np.linspace(np.log(0.05), np.log(20), 120))
    ll = [sum(plackett_luce_loglik(r, b) for r in races) for b in grid]
    best = int(np.argmax(ll))
    lo, hi = grid[max(best - 1, 0)], grid[min(best + 1, len(grid) - 1)]
    fine = np.linspace(lo, hi, 40)
    ll = [sum(plackett_luce_loglik(r, b) for r in races) for b in fine]
    return float(fine[int(np.argmax(ll))])
