# backend/app/db.py

import sqlite3
from pathlib import Path
from typing import List, Optional

from .settings import settings

DB_PATH = Path(settings.db_path)


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _columns(conn: sqlite3.Connection, table: str) -> List[str]:
    return [r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def _pk_column(conn: sqlite3.Connection, table: str) -> Optional[str]:
    # PRAGMA table_info: pk field is 1 for primary key column
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    for r in rows:
        if int(r["pk"]) == 1:
            return r["name"]
    return None


def _migrate_matches_add_match_id(conn: sqlite3.Connection) -> None:
    """
    If an old 'matches' table exists without 'match_id', migrate it to the new schema:
      matches(match_id PRIMARY KEY, competition, utc_date, status, home_team, away_team,
              home_team_id, away_team_id, home_score, away_score)

    We copy old PK column into match_id (commonly 'id').
    """
    if not _table_exists(conn, "matches"):
        return

    cols = _columns(conn, "matches")
    if "match_id" in cols:
        return  # already new enough

    old_pk = _pk_column(conn, "matches")
    if old_pk is None:
        # fallback: if column "id" exists use it, else give up with a clear error
        if "id" in cols:
            old_pk = "id"
        else:
            raise RuntimeError("Cannot migrate matches table: no primary key column found and no 'id' column.")

    # Rename old table
    conn.execute("ALTER TABLE matches RENAME TO matches_old")

    # Create new table with correct schema
    conn.execute(
        """
        CREATE TABLE matches (
            match_id INTEGER PRIMARY KEY,
            competition TEXT NOT NULL,
            utc_date TEXT NOT NULL,
            status TEXT NOT NULL,

            home_team TEXT NOT NULL,
            away_team TEXT NOT NULL,

            home_team_id INTEGER,
            away_team_id INTEGER,

            home_score INTEGER,
            away_score INTEGER
        )
        """
    )

    old_cols = _columns(conn, "matches_old")

    def has(c: str) -> bool:
        return c in old_cols

    # Build SELECT list with safe fallbacks
    # If some columns don't exist in old, fill with NULL/default.
    select_exprs = [
        f"{old_pk} AS match_id",
        "competition" if has("competition") else "NULL AS competition",
        "utc_date" if has("utc_date") else "NULL AS utc_date",
        "status" if has("status") else "'UNKNOWN' AS status",
        "home_team" if has("home_team") else "NULL AS home_team",
        "away_team" if has("away_team") else "NULL AS away_team",
        "home_team_id" if has("home_team_id") else "NULL AS home_team_id",
        "away_team_id" if has("away_team_id") else "NULL AS away_team_id",
        "home_score" if has("home_score") else "NULL AS home_score",
        "away_score" if has("away_score") else "NULL AS away_score",
    ]

    conn.execute(
        f"""
        INSERT INTO matches (
            match_id, competition, utc_date, status,
            home_team, away_team, home_team_id, away_team_id,
            home_score, away_score
        )
        SELECT {", ".join(select_exprs)}
        FROM matches_old
        """
    )

    # Drop old table
    conn.execute("DROP TABLE matches_old")


def init_db() -> None:
    conn = get_conn()
    cur = conn.cursor()

    # Ensure matches table exists (new schema)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS matches (
            match_id INTEGER PRIMARY KEY,
            competition TEXT NOT NULL,
            utc_date TEXT NOT NULL,
            status TEXT NOT NULL,

            home_team TEXT NOT NULL,
            away_team TEXT NOT NULL,

            home_team_id INTEGER,
            away_team_id INTEGER,

            home_score INTEGER,
            away_score INTEGER
        )
        """
    )

    # Run migration if the table existed in old format
    _migrate_matches_add_match_id(conn)

    # Elo ratings (by team_id)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS elo_ratings (
            competition TEXT NOT NULL,
            team_id INTEGER NOT NULL,
            team_name TEXT NOT NULL,
            rating REAL NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (competition, team_id)
        )
        """
    )

    conn.commit()
    conn.close()