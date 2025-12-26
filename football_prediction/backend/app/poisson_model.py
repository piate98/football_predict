import math
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

from .db import get_conn


@dataclass
class PoissonConfig:
    # how many recent matches per team to estimate attack/defence
    window_matches: int = 20

    # goal grid 0..max_goals used to approximate probabilities
    max_goals: int = 6

    # shrink team strengths towards 1.0 to reduce overfitting / home bias
    smoothing: float = 0.15

    # clamp lambdas to avoid extreme tails when data is sparse
    min_lambda: float = 0.2
    max_lambda: float = 4.0


def poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def build_score_matrix(lh: float, la: float, max_goals: int) -> List[List[float]]:
    mat: List[List[float]] = []
    for i in range(max_goals + 1):
        pi = poisson_pmf(i, lh)
        row = []
        for j in range(max_goals + 1):
            row.append(pi * poisson_pmf(j, la))
        mat.append(row)
    return mat


def derive_markets_from_matrix(mat: List[List[float]]) -> Dict[str, float]:
    """
    NOTE: You said you *don't want 1X2 shown for Poisson on the frontend*.
    That is a UI choice. Backend can still compute 1X2 internally, but we
    can also choose NOT to return p_home/p_draw/p_away in API response.

    This function returns them because they are mathematically useful, but
    you can omit them in app/main.py response mapping.
    """
    ph = pd_ = pa = over25 = btts = 0.0
    gmax = len(mat) - 1

    for i in range(gmax + 1):
        for j in range(gmax + 1):
            p = mat[i][j]
            if i > j:
                ph += p
            elif i == j:
                pd_ += p
            else:
                pa += p

            if i + j >= 3:
                over25 += p
            if i >= 1 and j >= 1:
                btts += p

    total = ph + pd_ + pa
    if total > 0:
        ph /= total
        pd_ /= total
        pa /= total
        over25 /= total
        btts /= total

    return {
        "p_home": ph,
        "p_draw": pd_,
        "p_away": pa,
        "p_over25": over25,
        "p_btts": btts,
        "mass_captured": total,
    }


def top_scorelines(mat: List[List[float]], top_n: int = 5) -> List[Dict[str, float]]:
    items: List[Tuple[int, int, float]] = []
    gmax = len(mat) - 1
    for i in range(gmax + 1):
        for j in range(gmax + 1):
            items.append((i, j, mat[i][j]))
    items.sort(key=lambda x: x[2], reverse=True)
    return [{"home_goals": i, "away_goals": j, "p": p} for i, j, p in items[:top_n]]


def _league_averages(competition: str) -> Tuple[float, float]:
    conn = get_conn()
    row = conn.execute(
        """
        SELECT AVG(home_score) AS avg_h, AVG(away_score) AS avg_a
        FROM matches
        WHERE competition=?
          AND status='FINISHED'
          AND home_score IS NOT NULL AND away_score IS NOT NULL
        """,
        (competition,),
    ).fetchone()
    conn.close()

    avg_h = float(row["avg_h"]) if row and row["avg_h"] is not None else 1.4
    avg_a = float(row["avg_a"]) if row and row["avg_a"] is not None else 1.1
    return avg_h, avg_a


def _team_recent_rates_ids(
    competition: str, team_id: int, window: int
) -> Tuple[float, float, float, float]:
    """
    Returns:
      hh_scored, hh_conceded, aa_scored, aa_conceded
    (home-only and away-only splits for this team)
    """
    conn = get_conn()
    cur = conn.cursor()

    home_rows = cur.execute(
        """
        SELECT home_score, away_score
        FROM matches
        WHERE competition=?
          AND status='FINISHED'
          AND home_team_id=?
          AND home_score IS NOT NULL AND away_score IS NOT NULL
        ORDER BY utc_date DESC
        LIMIT ?
        """,
        (competition, team_id, window),
    ).fetchall()

    away_rows = cur.execute(
        """
        SELECT home_score, away_score
        FROM matches
        WHERE competition=?
          AND status='FINISHED'
          AND away_team_id=?
          AND home_score IS NOT NULL AND away_score IS NOT NULL
        ORDER BY utc_date DESC
        LIMIT ?
        """,
        (competition, team_id, window),
    ).fetchall()

    conn.close()

    def avg(vals: List[float], fallback: float) -> float:
        return sum(vals) / len(vals) if vals else fallback

    h_scored = [float(r["home_score"]) for r in home_rows]
    h_conc = [float(r["away_score"]) for r in home_rows]
    a_scored = [float(r["away_score"]) for r in away_rows]
    a_conc = [float(r["home_score"]) for r in away_rows]

    return (
        avg(h_scored, 0.0),
        avg(h_conc, 0.0),
        avg(a_scored, 0.0),
        avg(a_conc, 0.0),
    )


def estimate_lambdas(
    competition: str, home_id: int, away_id: int, cfg: Optional[PoissonConfig] = None
) -> Tuple[float, float]:
    """
    Estimate expected goals:
      lambda_home, lambda_away

    Uses:
      - league average home/away goals
      - home team's recent HOME attack/defence
      - away team's recent AWAY attack/defence
      - smoothing to reduce bias/overfitting
    """
    cfg = cfg or PoissonConfig()
    avg_h, avg_a = _league_averages(competition)

    hh_sc, hh_cc, _, _ = _team_recent_rates_ids(competition, home_id, cfg.window_matches)
    _, _, aa_sc, aa_cc = _team_recent_rates_ids(competition, away_id, cfg.window_matches)

    # If sparse, fall back to league typical
    if hh_sc == 0.0 and hh_cc == 0.0:
        hh_sc, hh_cc = avg_h, avg_a
    if aa_sc == 0.0 and aa_cc == 0.0:
        aa_sc, aa_cc = avg_a, avg_h

    # Strength multipliers relative to league
    home_attack = (hh_sc / avg_h) if avg_h > 0 else 1.0
    home_def_weak = (hh_cc / avg_a) if avg_a > 0 else 1.0

    away_attack = (aa_sc / avg_a) if avg_a > 0 else 1.0
    away_def_weak = (aa_cc / avg_h) if avg_h > 0 else 1.0

    # Smooth toward 1.0 (reduces strong home tilt when few games)
    def smooth(x: float) -> float:
        a = cfg.smoothing
        return (1.0 - a) * x + a * 1.0

    home_attack = smooth(home_attack)
    away_def_weak = smooth(away_def_weak)
    away_attack = smooth(away_attack)
    home_def_weak = smooth(home_def_weak)

    lam_home = avg_h * home_attack * away_def_weak
    lam_away = avg_a * away_attack * home_def_weak

    # clamp
    lam_home = max(cfg.min_lambda, min(cfg.max_lambda, lam_home))
    lam_away = max(cfg.min_lambda, min(cfg.max_lambda, lam_away))

    return lam_home, lam_away