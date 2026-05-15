from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from typing import Any

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


def dollars_to_cents(value: str | int | float | None) -> int | None:
    if value is None:
        return None
    return int(round(float(value) * 100))


def quantity_to_int(value: str | int | float | None) -> int:
    if value is None:
        return 0
    return int(float(value))


@dataclass(frozen=True)
class ParsedOrderbook:
    yes: dict[int, int]
    no: dict[int, int]
    best_yes_bid: int | None
    best_no_bid: int | None
    best_yes_ask: int | None
    best_no_ask: int | None


class KalshiClient:
    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        private_key_pem: str | None = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.private_key_pem = private_key_pem
        self.timeout_seconds = timeout_seconds

    def _headers(self, method: str, path: str) -> dict[str, str]:
        if not self.api_key or not self.private_key_pem:
            return {}

        timestamp = str(int(time.time() * 1000))
        key_text = self.private_key_pem.replace("\\n", "\n").encode()
        private_key = serialization.load_pem_private_key(key_text, password=None)
        message = f"{timestamp}{method.upper()}{path}".encode()
        signature = private_key.sign(
            message,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )
        return {
            "KALSHI-ACCESS-KEY": self.api_key,
            "KALSHI-ACCESS-TIMESTAMP": timestamp,
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode(),
        }

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout_seconds) as client:
            response = await client.get(path, params=params, headers=self._headers("GET", path))
            response.raise_for_status()
            return response.json()

    async def get_market(self, ticker: str) -> dict[str, Any]:
        return await self._get(f"/markets/{ticker}")

    async def list_markets(
        self, series_ticker: str, status: str = "open", limit: int = 200, cursor: str | None = None
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"series_ticker": series_ticker, "status": status, "limit": limit}
        if cursor:
            params["cursor"] = cursor
        return await self._get("/markets", params=params)

    async def get_orderbook(self, ticker: str) -> ParsedOrderbook:
        payload = await self._get(f"/markets/{ticker}/orderbook")
        return parse_orderbook(payload)

    async def get_trades(self, ticker: str, limit: int = 100) -> dict[str, Any]:
        return await self._get("/markets/trades", params={"ticker": ticker, "limit": limit})


def parse_orderbook(payload: dict[str, Any]) -> ParsedOrderbook:
    if "orderbook_fp" in payload:
        raw = payload["orderbook_fp"]
        yes = {dollars_to_cents(price) or 0: quantity_to_int(qty) for price, qty in raw.get("yes_dollars", [])}
        no = {dollars_to_cents(price) or 0: quantity_to_int(qty) for price, qty in raw.get("no_dollars", [])}
    else:
        raw = payload.get("orderbook", {})
        yes_raw = raw.get("yes", {})
        no_raw = raw.get("no", {})
        if isinstance(yes_raw, dict):
            yes_levels = yes_raw.get("bids", [])
        else:
            yes_levels = yes_raw
        if isinstance(no_raw, dict):
            no_levels = no_raw.get("bids", [])
        else:
            no_levels = no_raw
        yes = {int(price): quantity_to_int(qty) for price, qty in yes_levels}
        no = {int(price): quantity_to_int(qty) for price, qty in no_levels}

    yes.pop(0, None)
    no.pop(0, None)
    best_yes_bid = max(yes) if yes else None
    best_no_bid = max(no) if no else None
    best_yes_ask = 100 - best_no_bid if best_no_bid is not None else None
    best_no_ask = 100 - best_yes_bid if best_yes_bid is not None else None
    return ParsedOrderbook(
        yes=yes,
        no=no,
        best_yes_bid=best_yes_bid,
        best_no_bid=best_no_bid,
        best_yes_ask=best_yes_ask,
        best_no_ask=best_no_ask,
    )
