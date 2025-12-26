from __future__ import annotations
from datetime import date, timedelta, datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
import asyncio
import re

from .db import get_conn
from .football_data import FootballDataClient
from .elo import EloConfig, update_elo, DEFAULT_RATING


def _extract_score(match: Dict[str, Any]) -> Tuple[Optional[int], Optional[int]]:
    score = match.get("score") or {}
    ft = score.get("fullTime") or {}
    home = ft.get("home")
    away = ft.get("away")
    if home is None or away is None:
        return None, None
    try:
        return int(home), int(away)
    except Exception:
        return None, None


def _parse_retry_seconds(msg: str) -> int:
    m = re.search(r"Wait\s+(\d+)\s+seconds", msg)
    if m:
        return max(1, int(m.group(1)))
    return 60


async def _get_matches_with_retry(client: FootballDataClient, competition: str, d1: date, d2: date) -> List[Dict[str, Any]]:
    while True:
        try:
            return await client.get_matches(competition=competition, date_from=d1, date_to=d2)
        except RuntimeError as e:
            s = str(e)
            if s.startswith("429"):
                wait_s = _parse_retry_seconds(s)
                await asyncio.sleep(wait_s + 1)
                continue
            raise


async def upsert_matches_from_api(competition: str, days_back: int = 365) -> int:
    client = FootballDataClient()

    end = date.today()
    start = end - timedelta(days=days_back)

    # fewer calls
    chunk_days = 180

    all_matches: List[Dict[str, Any]] = []
    cur = start
    while cur <= end:
        cur_end = min(end, cur + timedelta(days=chunk_days))
        chunk = await _get_matches_with_retry(client, competition, cur, cur_end)
        all_matches.extend(chunk)
        cur = cur_end + timedelta(days=1)

    finished = [m for m in all_matches if m.get("status") == "FINISHED"]

    conn = get_conn()
    inserted = 0

    for m in finished:
        match_id = m.get("id")
        utc_date = m.get("utcDate")
        status = m.get("status")

        home = (m.get("homeTeam") or {})
        away = (m.get("awayTeam") or {})

        home_team = home.get("name")
        away_team = away.get("name")
        home_team_id = home.get("id")
        away_team_id = away.get("id")

        home_score, away_score = _extract_score(m)

        if not match_id or not utc_date or not home_team or not away_team:
            continue
        if home_team_id is None or away_team_id is None:
            continue
        if home_score is None or away_score is None:
            continue

        conn.execute(
            """
            INSERT INTO matches (match_id, competition, utc_date, status,
                                home_team, away_team, home_team_id, away_team_id,
                                home_score, away_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(match_id) DO UPDATE SET
                competition=excluded.competition,
                utc_date=excluded.utc_date,
                status=excluded.status,
                home_team=excluded.home_team,
                away_team=excluded.away_team,
                home_team_id=excluded.home_team_id,
                away_team_id=excluded.away_team_id,
                home_score=excluded.home_score,
                away_score=excluded.away_score
            """,
            (match_id, competition, utc_date, status,
             home_team, away_team, int(home_team_id), int(away_team_id),
             int(home_score), int(away_score))
        )
        inserted += 1

    conn.commit()
    conn.close()
    return inserted


def rebuild_elo_from_matches(competition: str) -> int:
    conn = get_conn()
    conn.execute("DELETE FROM elo_ratings WHERE competition=?", (competition,))
    conn.commit()

    rows = conn.execute(
        """
        SELECT utc_date,
               home_team_id, away_team_id,
               home_team, away_team,
               home_score, away_score
        FROM matches
        WHERE competition=?
          AND status='FINISHED'
AND home_score IS NOT NULL
          AND away_score IS NOT NULL
          AND home_team_id IS NOT NULL
          AND away_team_id IS NOT NULL
        ORDER BY utc_date ASC
        """,
        (competition,)
    ).fetchall()

    cfg = EloConfig()
    ratings: Dict[int, float] = {}
    names: Dict[int, str] = {}

    def r(team_id: int) -> float:
        return ratings.get(team_id, DEFAULT_RATING)

    for row in rows:
        hid = int(row["home_team_id"])
        aid = int(row["away_team_id"])
        hs = int(row["home_score"])
        ag = int(row["away_score"])

        names[hid] = row["home_team"]
        names[aid] = row["away_team"]

        rh = r(hid)
        ra = r(aid)
        rh2, ra2 = update_elo(rh, ra, hs, ag, cfg)
        ratings[hid] = rh2
        ratings[aid] = ra2

    now = datetime.now(timezone.utc).isoformat()
    for team_id, rating in ratings.items():
        conn.execute(
            """
            INSERT INTO elo_ratings (competition, team_id, team_name, rating, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(competition, team_id) DO UPDATE SET
                team_name=excluded.team_name,
                rating=excluded.rating,
                updated_at=excluded.updated_at
            """,
            (competition, int(team_id), names.get(team_id, str(team_id)), float(rating), now)
        )

    conn.commit()
    n = conn.execute(
        "SELECT COUNT(*) AS n FROM elo_ratings WHERE competition=?",
        (competition,)
    ).fetchone()["n"]
    conn.close()
    return int(n)