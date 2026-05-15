from __future__ import annotations

from typing import Any

import httpx


class OpticOddsClient:
    def __init__(self, base_url: str, api_key: str | None, timeout_seconds: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def _headers(self) -> dict[str, str]:
        return {"x-api-key": self.api_key} if self.api_key else {}

    async def _get(self, path: str, params: dict[str, Any] | list[tuple[str, Any]] | None = None) -> dict[str, Any]:
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout_seconds) as client:
            response = await client.get(path, params=params, headers=self._headers())
            response.raise_for_status()
            return response.json()

    async def fixtures(
        self,
        league: str,
        start_date_after: str | None = None,
        start_date_before: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"league": league, "limit": limit}
        if start_date_after:
            params["start_date_after"] = start_date_after
        if start_date_before:
            params["start_date_before"] = start_date_before
        return await self._get("/fixtures", params=params)

    async def fixture_odds(
        self,
        fixture_id: str,
        sportsbooks: list[str],
        market: str,
        is_main: bool | None = True,
    ) -> dict[str, Any]:
        params: list[tuple[str, Any]] = [("fixture_id", fixture_id), ("market", market)]
        for sportsbook in sportsbooks:
            params.append(("sportsbook", sportsbook))
        if is_main is not None:
            params.append(("is_main", "true" if is_main else "false"))
        return await self._get("/fixtures/odds", params=params)
