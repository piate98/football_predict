# backend/app/main.py

from datetime import date, timedelta
from typing import Optional, List, Dict, Any
import os

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from .db import init_db, get_conn
from .settings import settings
from .football_data import FootballDataClient

from .elo import EloConfig, probs_1x2, DEFAULT_RATING
from .train_jobs import upsert_matches_from_api, rebuild_elo_from_matches

from .poisson_model import (
    PoissonConfig,
    estimate_lambdas,
    build_score_matrix,
    derive_markets_from_matrix,
    top_scorelines,
)

app = FastAPI(title="Football Prediction API", version="0.5.2")


@app.on_event("startup")
def _startup():
    init_db()


# ----------------------------
# Helpers
# ----------------------------
def get_rating(competition: str, team_id: int) -> float:
    conn = get_conn()
    row = conn.execute(
        "SELECT rating FROM elo_ratings WHERE competition=? AND team_id=?",
        (competition, int(team_id)),
    ).fetchone()
    conn.close()
    return float(row["rating"]) if row else DEFAULT_RATING


def _is_rate_limit_error(e: Exception) -> bool:
    s = str(e)
    # our client/train code raises RuntimeError("429 from provider. Body: ...")
    return s.startswith("429") or '"errorCode":429' in s or "errorCode\":429" in s


def _parse_league_list(raw: str) -> List[str]:
    # "PL,BL1,SA,PD,FL1" -> ["PL","BL1","SA","PD","FL1"]
    items = []
    for x in (raw or "").split(","):
        x = x.strip()
        if x:
            items.append(x)
    return items


def _default_train_leagues() -> List[str]:
    # You can override via env var on Render:
    # TRAIN_LEAGUES="PL,BL1,SA,PD,FL1"
    raw = os.getenv("TRAIN_LEAGUES", "").strip()
    if raw:
        return _parse_league_list(raw)

    # sensible default set (top leagues)
    return ["PL", "BL1", "SA", "PD", "FL1"]


# ----------------------------
# Schemas
# ----------------------------
class ScorelineOut(BaseModel):
    home_goals: int
    away_goals: int
    p: float


class FixtureOut(BaseModel):
    match_id: int
    utc_date: str
    competition: str
    status: str

    home_team: str
    away_team: str
    home_team_id: int
    away_team_id: int

    # Elo baseline
    elo_p_home: float
    elo_p_draw: float
    elo_p_away: float

    # Poisson upgrade
    xg_home: float
    xg_away: float
    p_home: float
    p_draw: float
    p_away: float
    p_over25: float
    p_btts: float
    mass_captured: float
    top_scores: List[ScorelineOut]


class TrainRequest(BaseModel):
    competition: str
    days_back: int = 365


class TrainAllRequest(BaseModel):
    # optional override; if not provided -> env TRAIN_LEAGUES or defaults
    competitions: Optional[List[str]] = None
    days_back: int = 365


# ----------------------------
# Routes
# ----------------------------
@app.get("/health")
def health():
    # Simple health endpoint for Render + debugging
    return {"ok": True, "service": "football_prediction_api"}


@app.get("/api/debug_token")
def debug_token():
    t = settings.football_data_token
    return {"token_last4": t[-4:], "token_len": len(t)}


@app.get("/api/db_stats")
def db_stats(competition: str):
    conn = get_conn()
    row = conn.execute(
        """
        SELECT
          COUNT(*) AS total,
          SUM(CASE WHEN status='FINISHED' THEN 1 ELSE 0 END) AS finished,
          SUM(CASE WHEN status='FINISHED' AND home_team_id IS NOT NULL AND away_team_id IS NOT NULL THEN 1 ELSE 0 END) AS finished_with_ids,
          SUM(CASE WHEN status='FINISHED' AND home_score IS NOT NULL AND away_score IS NOT NULL THEN 1 ELSE 0 END) AS finished_with_scores
        FROM matches
        WHERE competition=?
        """,
        (competition,),
    ).fetchone()
    conn.close()
    return dict(row)


@app.get("/api/team_rating")
def team_rating(
    competition: str = Query(...),
    team_id: int = Query(..., description="Team ID from football-data.org"),
):
    return {"competition": competition, "team_id": team_id, "rating": get_rating(competition, team_id)}


@app.get("/api/leagues")
async def leagues() -> Dict[str, Any]:
    client = FootballDataClient()
    try:
        comps = await client.get_competitions()
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=f"Upstream API error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")

    leagues_out = []
    for c in comps:
        leagues_out.append(
            {
                "code": c.get("code"),
                "id": c.get("id"),
                "name": c.get("name"),
                "area": (c.get("area") or {}).get("name"),
            }
        )

    leagues_out = [x for x in leagues_out if x.get("code")]
    return {"leagues": leagues_out}


@app.get("/api/fixtures", response_model=List[FixtureOut])
async def fixtures(
    competition: str = Query(..., description="Competition code from /api/leagues (e.g., BL1)"),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
):
    # default window: 30 days
    if date_from is None:
        date_from = date.today()
    if date_to is None:
        date_to = date_from + timedelta(days=30)

    client = FootballDataClient()
    try:
        matches = await client.get_matches(competition=competition, date_from=date_from, date_to=date_to)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=f"Upstream API error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")

    UPCOMING = {"SCHEDULED", "TIMED"}
    matches = [m for m in matches if m.get("status") in UPCOMING]

    elo_cfg = EloConfig()
    # NOTE: if you previously got a "unexpected keyword smoothing",
    # it means your PoissonConfig did not have smoothing in that file.
    # Ensure poisson_model.py includes smoothing in the dataclass.
    pois_cfg = PoissonConfig(window_matches=20, max_goals=6, smoothing=0.15)

    out: List[FixtureOut] = []
    for m in matches:
        home_obj = m.get("homeTeam") or {}
        away_obj = m.get("awayTeam") or {}

        home_team = home_obj.get("name")
        away_team = away_obj.get("name")
        home_id = home_obj.get("id")
        away_id = away_obj.get("id")

        if not home_team or not away_team or home_id is None or away_id is None:
            continue

        # --- Elo baseline (by team_id) ---
        rh = get_rating(competition, int(home_id))
        ra = get_rating(competition, int(away_id))
        elo_p = probs_1x2(rh, ra, elo_cfg)

        # --- Poisson upgrade (by team_id) ---
        lam_h, lam_a = estimate_lambdas(competition, int(home_id), int(away_id), pois_cfg)
        mat = build_score_matrix(lam_h, lam_a, pois_cfg.max_goals)
        markets = derive_markets_from_matrix(mat)
        tops = top_scorelines(mat, top_n=5)

        out.append(
            FixtureOut(
                match_id=int(m["id"]),
                utc_date=m["utcDate"],
                competition=competition,
                status=m["status"],
                home_team=home_team,
                away_team=away_team,
                home_team_id=int(home_id),
                away_team_id=int(away_id),
                elo_p_home=round(elo_p["home"], 4),
                elo_p_draw=round(elo_p["draw"], 4),
                elo_p_away=round(elo_p["away"], 4),
                xg_home=round(lam_h, 3),
                xg_away=round(lam_a, 3),
                p_home=round(markets["p_home"], 4),
                p_draw=round(markets["p_draw"], 4),
                p_away=round(markets["p_away"], 4),
                p_over25=round(markets["p_over25"], 4),
                p_btts=round(markets["p_btts"], 4),
                mass_captured=round(markets["mass_captured"], 4),
                top_scores=[
                    ScorelineOut(
                        home_goals=int(t["home_goals"]),
                        away_goals=int(t["away_goals"]),
                        p=round(float(t["p"]), 6),
                    )
                    for t in tops
                ],
            )
        )

    return out


@app.post("/api/rebuild")
def rebuild_only(competition: str = Query(..., description="Competition code like BL1")):
    """
    Rebuild Elo from whatever is already in the local DB.
    Zero upstream calls.
    """
    try:
        n_teams = rebuild_elo_from_matches(competition)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rebuild failed: {e}")
    return {"competition": competition, "teams_in_elo_table": n_teams}


@app.post("/api/train")
async def train(req: TrainRequest) -> Dict[str, Any]:
    """
    Train = (1) try to fetch finished matches into DB, (2) rebuild Elo.
    If provider rate-limits (429), we DO NOT fail:
      - we skip fetching
      - we still rebuild from local DB
    """
    inserted = 0
    fetch_skipped_due_to_rate_limit = False
    fetch_error: Optional[str] = None

    try:
        inserted = await upsert_matches_from_api(req.competition, days_back=req.days_back)
    except RuntimeError as e:
        if _is_rate_limit_error(e):
            fetch_skipped_due_to_rate_limit = True
            fetch_error = str(e)
        else:
            raise HTTPException(status_code=502, detail=f"Training upstream error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Training failed: {e}")

    # always rebuild from DB
    try:
        n_teams = rebuild_elo_from_matches(req.competition)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Elo rebuild failed: {e}")

    stats = db_stats(req.competition)

    return {
        "competition": req.competition,
        "matches_upserted": inserted,
        "fetch_skipped_due_to_rate_limit": fetch_skipped_due_to_rate_limit,
        "fetch_error": fetch_error,
        "teams_in_elo_table": n_teams,
        "db_stats": stats,
    }


@app.post("/api/train_all")
async def train_all(req: TrainAllRequest) -> Dict[str, Any]:
    """
    Multi-league training for cron.

    - Tries to fetch finished matches for each competition
    - Rebuilds Elo for each competition
    - Continues even if one league fails
    - If rate-limited (429) on a league: skips fetch, still rebuilds from DB
    """
    competitions = req.competitions if (req.competitions and len(req.competitions)) else _default_train_leagues()

    results: List[Dict[str, Any]] = []
    totals = {
        "leagues_requested": len(competitions),
        "matches_upserted_total": 0,
        "rate_limited_count": 0,
        "failed_count": 0,
    }

    for comp in competitions:
        comp = (comp or "").strip()
        if not comp:
            continue

        inserted = 0
        fetch_skipped_due_to_rate_limit = False
        fetch_error: Optional[str] = None
        rebuild_error: Optional[str] = None
        n_teams: Optional[int] = None
        stats: Optional[Dict[str, Any]] = None

        # 1) fetch + upsert
        try:
            inserted = await upsert_matches_from_api(comp, days_back=req.days_back)
        except RuntimeError as e:
            if _is_rate_limit_error(e):
                fetch_skipped_due_to_rate_limit = True
                fetch_error = str(e)
                totals["rate_limited_count"] += 1
            else:
                fetch_error = str(e)
        except Exception as e:
            fetch_error = str(e)

        # 2) rebuild from DB always (even if fetch failed/limited)
        try:
            n_teams = rebuild_elo_from_matches(comp)
        except Exception as e:
            rebuild_error = str(e)

        # 3) stats
        try:
            stats = db_stats(comp)
        except Exception as e:
            stats = {"error": str(e)}

        ok = (rebuild_error is None)  # rebuild is the critical part
        if not ok:
            totals["failed_count"] += 1

        totals["matches_upserted_total"] += int(inserted)

        results.append(
            {
                "competition": comp,
                "ok": ok,
                "matches_upserted": inserted,
                "fetch_skipped_due_to_rate_limit": fetch_skipped_due_to_rate_limit,
                "fetch_error": fetch_error,
                "teams_in_elo_table": n_teams,
                "rebuild_error": rebuild_error,
                "db_stats": stats,
            }
        )

    return {"days_back": req.days_back, "competitions": competitions, "totals": totals, "results": results}

    