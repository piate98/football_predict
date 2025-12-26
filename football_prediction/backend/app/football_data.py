import httpx
import re
import asyncio
from datetime import date
from typing import Any, Dict, List, Optional
from .settings import settings

BASE = "https://api.football-data.org/v4"


def _clean_token(token: str) -> str:
    token = (token or "").strip()
    if (token.startswith('"') and token.endswith('"')) or (token.startswith("'") and token.endswith("'")):
        token = token[1:-1].strip()
    return token


def _parse_wait_seconds_from_body(text: str) -> int:
    # Example: {"message":"You reached your request limit. Wait 56 seconds.","errorCode":429}
    m = re.search(r"Wait\s+(\d+)\s+seconds", text or "")
    if m:
        try:
            return max(1, int(m.group(1)))
        except Exception:
            pass
    return 60


class FootballDataClient:
    """
    Rate-limit safe client:
    - Automatically retries 429 with provider-suggested delay
    - Uses Retry-After header when provided
    """

    def __init__(self) -> None:
        self.headers = {"X-Auth-Token": _clean_token(settings.football_data_token)}

    async def _get(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        max_retries: int = 6,
    ) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=25.0) as client:
            for attempt in range(max_retries):
                r = await client.get(url, headers=self.headers, params=params)

                # --- Handle rate limit (429) ---
                if r.status_code == 429:
                    retry_after = r.headers.get("Retry-After")
                    if retry_after and retry_after.isdigit():
                        wait_s = int(retry_after)
                    else:
                        wait_s = _parse_wait_seconds_from_body(r.text)

                    # sleep then retry
                    await asyncio.sleep(wait_s + 1)
                    continue

                # --- Other errors ---
                if r.status_code >= 400:
                    body = r.text[:1200]
                    raise RuntimeError(f"{r.status_code} from provider. Body: {body}")

                return r.json() if r.content else {}

            raise RuntimeError("429 from provider too many times; try again later.")

    async def get_competitions(self) -> List[Dict[str, Any]]:
        url = f"{BASE}/competitions"
        data = await self._get(url)
        return (data or {}).get("competitions", [])

    async def get_matches(
        self,
        competition: str,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        """
        NOTE: We intentionally do NOT pass `status` to provider.
        Some competitions return 400 with status filters.
        We filter statuses locally.
        """
        params: Dict[str, Any] = {}
        if date_from:
            params["dateFrom"] = date_from.isoformat()
        if date_to:
            params["dateTo"] = date_to.isoformat()

        url = f"{BASE}/competitions/{competition}/matches"
        data = await self._get(url, params=params)
        return (data or {}).get("matches", [])