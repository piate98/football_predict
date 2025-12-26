import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Tuple

DEFAULT_RATING = 1500.0

@dataclass
class EloConfig:
    k: float = 25.0
    home_adv: float = 60.0   # home advantage in Elo points
    draw_base: float = 0.26  # baseline draw probability

def expected_score(r_a: float, r_b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((r_b - r_a) / 400.0))

def update_elo(
    r_home: float,
    r_away: float,
    home_goals: int,
    away_goals: int,
    cfg: EloConfig
) -> Tuple[float, float]:
    if home_goals > away_goals:
        s_home, s_away = 1.0, 0.0
    elif home_goals < away_goals:
        s_home, s_away = 0.0, 1.0
    else:
        s_home, s_away = 0.5, 0.5

    e_home = expected_score(r_home + cfg.home_adv, r_away)
    e_away = 1.0 - e_home

    r_home_new = r_home + cfg.k * (s_home - e_home)
    r_away_new = r_away + cfg.k * (s_away - e_away)
    return r_home_new, r_away_new

def probs_1x2(r_home: float, r_away: float, cfg: EloConfig) -> Dict[str, float]:
    e_home = expected_score(r_home + cfg.home_adv, r_away)

    diff = abs((r_home + cfg.home_adv) - r_away)
    closeness = math.exp(-diff / 250.0)
    p_draw = min(0.38, max(0.12, cfg.draw_base + 0.12 * closeness))

    remaining = 1.0 - p_draw
    p_home = remaining * e_home
    p_away = remaining * (1.0 - e_home)

    s = p_home + p_draw + p_away
    return {"home": p_home / s, "draw": p_draw / s, "away": p_away / s}

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()