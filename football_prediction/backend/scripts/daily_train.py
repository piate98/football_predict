#!/usr/bin/env python3
"""
Daily trainer for football_prediction backend.

- Fetches recent matches for each league (days_back_recent)
- Upserts them into SQLite
- Rebuilds Elo ratings for each league
- (Optional) rebuilds Poisson team stats if your project has that step

Run:
  python scripts/daily_train.py --competitions BL1 FL1 PL SA PD --days-back-recent 60

Bootstrap (run once):
  python scripts/daily_train.py --competitions BL1 FL1 PL SA PD --days-back-recent 730 --bootstrap
"""

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
import traceback
from typing import Iterable

# --- FORCE backend/ as import root (so `import app...` works anywhere) ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # backend/
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
# ----------------------------------------------------------------------

from app.db import init_db
from app.train_jobs import upsert_matches_from_api, rebuild_elo_from_matches


DEFAULT_COMPETITIONS = ["BL1", "FL1", "PL", "SA", "PD"]


def is_rate_limit_error(e: Exception) -> bool:
    msg = str(e).lower()
    return (
        "429" in msg
        or "too many requests" in msg
        or "request limit" in msg
        or "reached your request limit" in msg
        or "wait" in msg and "seconds" in msg
    )


async def run_one_competition_async(comp: str, days_back: int) -> None:
    """
    Runs:
      - upsert matches from API -> DB  (ASYNC)
      - rebuild Elo from DB matches     (SYNC)
    """
    print(f"\n=== {comp}: upsert last {days_back} days ===")
    upsert_res = await upsert_matches_from_api(competition=comp, days_back=days_back)
    print(f"{comp}: upsert result: {upsert_res}")

    print(f"=== {comp}: rebuild Elo ===")
    elo_res = rebuild_elo_from_matches(competition=comp)
    print(f"{comp}: elo rebuild: {elo_res}")


async def safe_run_async(
    competitions: Iterable[str],
    days_back: int,
    max_retries: int = 6,
    base_sleep: float = 8.0,
) -> int:
    """
    Retries on provider rate-limit errors (429) with exponential backoff.
    Returns exit code (0 ok, 1 failed).
    """
    init_db()

    for comp in competitions:
        attempt = 0
        while True:
            try:
                await run_one_competition_async(comp, days_back=days_back)
                break
            except Exception as e:
                attempt += 1
                if is_rate_limit_error(e) and attempt <= max_retries:
                    sleep_s = base_sleep * (2 ** (attempt - 1))
                    sleep_s = min(sleep_s, 120.0)
                    print(f"[{comp}] Rate limited (attempt {attempt}/{max_retries}). Sleeping {sleep_s:.0f}s…")
                    await asyncio.sleep(sleep_s)
                    continue

                print(f"[{comp}] FAILED: {e}")
                traceback.print_exc()
                return 1

    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--competitions", nargs="*", default=DEFAULT_COMPETITIONS)
    ap.add_argument("--days-back-recent", type=int, default=60)
    ap.add_argument("--bootstrap", action="store_true", help="Bootstrap mode (informational flag).")
    args = ap.parse_args()

    comps = args.competitions
    days_back = args.days_back_recent

    print("Competitions:", comps)
    print("Days back:", days_back)
    if args.bootstrap:
        print("BOOTSTRAP MODE")

    code = asyncio.run(safe_run_async(comps, days_back=days_back))
    raise SystemExit(code)


if __name__ == "__main__":
    main()