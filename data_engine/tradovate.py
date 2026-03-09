"""Tradovate API Client for PropEdge.

Handles authentication, real-time WebSocket data, and order management.
TopstepX uses Tradovate as their execution platform.

Connection modes:
- Demo: https://demo.tradovateapi.com/v1 (free sandbox)
- Live: https://live.tradovateapi.com/v1 (real money)

Authentication: OAuth2 with device auth flow
WebSocket: Real-time market data + order updates
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)


# ── Configuration ────────────────────────────────────────────────────────

DEMO_API_URL = "https://demo.tradovateapi.com/v1"
LIVE_API_URL = "https://live.tradovateapi.com/v1"
DEMO_WS_URL = "wss://demo.tradovateapi.com/v1/websocket"
LIVE_WS_URL = "wss://live.tradovateapi.com/v1/websocket"
DEMO_MD_URL = "wss://md-d.tradovateapi.com/v1/websocket"
LIVE_MD_URL = "wss://md.tradovateapi.com/v1/websocket"


@dataclass
class TradovateConfig:
    """Tradovate API configuration."""
    api_url: str = DEMO_API_URL
    ws_url: str = DEMO_WS_URL
    md_url: str = DEMO_MD_URL
    username: str = ""
    password: str = ""
    app_id: str = ""
    app_version: str = "1.0"
    cid: str = ""           # Client ID
    sec: str = ""           # Client secret
    device_id: str = ""
    is_live: bool = False

    @classmethod
    def from_env(cls) -> "TradovateConfig":
        """Load config from environment variables."""
        is_live = os.getenv("TRADOVATE_LIVE", "false").lower() == "true"
        return cls(
            api_url=LIVE_API_URL if is_live else DEMO_API_URL,
            ws_url=LIVE_WS_URL if is_live else DEMO_WS_URL,
            md_url=LIVE_MD_URL if is_live else DEMO_MD_URL,
            username=os.getenv("TRADOVATE_USERNAME", ""),
            password=os.getenv("TRADOVATE_PASSWORD", ""),
            app_id=os.getenv("TRADOVATE_APP_ID", ""),
            app_version=os.getenv("TRADOVATE_APP_VERSION", "1.0"),
            cid=os.getenv("TRADOVATE_CID", ""),
            sec=os.getenv("TRADOVATE_SEC", ""),
            device_id=os.getenv("TRADOVATE_DEVICE_ID", "propedge-v2"),
            is_live=is_live,
        )


# ── Authentication ───────────────────────────────────────────────────────

@dataclass
class AuthToken:
    """Tradovate authentication token."""
    access_token: str = ""
    expiration_time: datetime = field(default_factory=datetime.now)
    user_id: int = 0
    name: str = ""

    @property
    def is_expired(self) -> bool:
        return datetime.now() >= self.expiration_time - timedelta(minutes=5)


class TradovateAuth:
    """Handles Tradovate OAuth2 authentication."""

    def __init__(self, config: TradovateConfig):
        self.config = config
        self.token: Optional[AuthToken] = None

    async def authenticate(self) -> AuthToken:
        """Get access token via username/password auth."""
        url = f"{self.config.api_url}/auth/accesstokenrequest"
        payload = {
            "name": self.config.username,
            "password": self.config.password,
            "appId": self.config.app_id,
            "appVersion": self.config.app_version,
            "cid": self.config.cid,
            "sec": self.config.sec,
            "deviceId": self.config.device_id,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise ConnectionError(f"Auth failed ({resp.status}): {text}")

                data = await resp.json()

                if "errorText" in data:
                    raise ConnectionError(f"Auth error: {data['errorText']}")

                self.token = AuthToken(
                    access_token=data["accessToken"],
                    expiration_time=datetime.fromisoformat(
                        data["expirationTime"].replace("Z", "+00:00")
                    ),
                    user_id=data.get("userId", 0),
                    name=data.get("name", ""),
                )

                logger.info(f"Authenticated as {self.token.name} (user {self.token.user_id})")
                return self.token

    async def ensure_token(self) -> str:
        """Get a valid access token, refreshing if needed."""
        if self.token is None or self.token.is_expired:
            await self.authenticate()
        return self.token.access_token

    def get_headers(self) -> Dict[str, str]:
        """Get auth headers for HTTP requests."""
        if not self.token:
            raise RuntimeError("Not authenticated. Call authenticate() first.")
        return {
            "Authorization": f"Bearer {self.token.access_token}",
            "Content-Type": "application/json",
        }


# ── REST Client ──────────────────────────────────────────────────────────

class TradovateREST:
    """Tradovate REST API client for orders and positions."""

    def __init__(self, config: TradovateConfig, auth: TradovateAuth):
        self.config = config
        self.auth = auth

    async def _request(self, method: str, endpoint: str, data: Any = None) -> Any:
        """Make an authenticated API request."""
        url = f"{self.config.api_url}{endpoint}"
        headers = self.auth.get_headers()

        async with aiohttp.ClientSession() as session:
            if method == "GET":
                async with session.get(url, headers=headers) as resp:
                    return await resp.json()
            elif method == "POST":
                async with session.post(url, headers=headers, json=data) as resp:
                    return await resp.json()

    # ── Account ──────────────────────────────────────────────
    async def get_accounts(self) -> List[Dict]:
        """Get all trading accounts."""
        return await self._request("GET", "/account/list")

    async def get_account(self, account_id: int) -> Dict:
        """Get a specific account."""
        return await self._request("GET", f"/account/item?id={account_id}")

    async def get_cash_balance(self, account_id: int) -> Dict:
        """Get cash balance for an account."""
        return await self._request("GET", f"/cashBalance/getCashBalanceSnapshot?accountId={account_id}")

    # ── Positions ────────────────────────────────────────────
    async def get_positions(self) -> List[Dict]:
        """Get all open positions."""
        return await self._request("GET", "/position/list")

    async def get_position(self, position_id: int) -> Dict:
        """Get a specific position."""
        return await self._request("GET", f"/position/item?id={position_id}")

    # ── Orders ───────────────────────────────────────────────
    async def place_order(
        self,
        account_id: int,
        action: str,        # "Buy" or "Sell"
        symbol: str,         # e.g., "MESM5" (MES June 2025)
        order_qty: int,
        order_type: str,     # "Market", "Limit", "Stop", "StopLimit"
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        time_in_force: str = "Day",
    ) -> Dict:
        """Place a new order."""
        payload = {
            "accountSpec": self.config.username,
            "accountId": account_id,
            "action": action,
            "symbol": symbol,
            "orderQty": order_qty,
            "orderType": order_type,
            "timeInForce": time_in_force,
        }
        if price is not None:
            payload["price"] = price
        if stop_price is not None:
            payload["stopPrice"] = stop_price

        return await self._request("POST", "/order/placeOrder", payload)

    async def cancel_order(self, order_id: int) -> Dict:
        """Cancel an open order."""
        return await self._request("POST", "/order/cancelOrder", {"orderId": order_id})

    async def modify_order(
        self,
        order_id: int,
        order_qty: Optional[int] = None,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
    ) -> Dict:
        """Modify an existing order."""
        payload = {"orderId": order_id}
        if order_qty is not None:
            payload["orderQty"] = order_qty
        if price is not None:
            payload["price"] = price
        if stop_price is not None:
            payload["stopPrice"] = stop_price
        return await self._request("POST", "/order/modifyOrder", payload)

    async def flatten_position(self, account_id: int) -> Dict:
        """Flatten all positions for an account."""
        positions = await self.get_positions()
        results = []
        for pos in positions:
            if pos.get("netPos", 0) != 0:
                action = "Sell" if pos["netPos"] > 0 else "Buy"
                qty = abs(pos["netPos"])
                result = await self.place_order(
                    account_id=account_id,
                    action=action,
                    symbol=pos["contractId"],
                    order_qty=qty,
                    order_type="Market",
                )
                results.append(result)
        return {"flattened": len(results), "results": results}

    # ── Contracts ────────────────────────────────────────────
    async def find_contract(self, symbol: str) -> Dict:
        """Find a contract by symbol name (e.g., 'MESM5')."""
        return await self._request("GET", f"/contract/find?name={symbol}")

    async def get_contract_spec(self, symbol: str) -> Dict:
        """Get contract specification."""
        contract = await self.find_contract(symbol)
        if contract:
            return await self._request("GET", f"/contractMaturity/item?id={contract.get('contractMaturityId')}")
        return {}


# ── WebSocket Market Data ────────────────────────────────────────────────

class TradovateMarketData:
    """WebSocket client for real-time market data from Tradovate.

    Provides:
    - Real-time quotes (bid/ask/last)
    - DOM (depth of market) data
    - Chart/candle data streaming
    """

    def __init__(self, config: TradovateConfig, auth: TradovateAuth):
        self.config = config
        self.auth = auth
        self._ws = None
        self._callbacks: Dict[str, List[Callable]] = {}
        self._running = False
        self._request_id = 0

    def on(self, event: str, callback: Callable):
        """Register a callback for a market data event."""
        if event not in self._callbacks:
            self._callbacks[event] = []
        self._callbacks[event].append(callback)

    async def connect(self):
        """Connect to Tradovate market data WebSocket."""
        token = await self.auth.ensure_token()
        self._running = True

        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(self.config.md_url) as ws:
                self._ws = ws

                # Authorize the WebSocket connection
                await ws.send_str(f"authorize\n0\n\n{token}")

                logger.info("Connected to Tradovate market data WebSocket")

                async for msg in ws:
                    if not self._running:
                        break

                    if msg.type == aiohttp.WSMsgType.TEXT:
                        await self._handle_message(msg.data)
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        logger.error(f"WebSocket error: {ws.exception()}")
                        break

    async def disconnect(self):
        """Disconnect from WebSocket."""
        self._running = False
        if self._ws:
            await self._ws.close()

    async def subscribe_quotes(self, symbol: str):
        """Subscribe to real-time quotes for a symbol."""
        if self._ws:
            self._request_id += 1
            msg = f"md/subscribeQuote\n{self._request_id}\n\n{{\"symbol\":\"{symbol}\"}}"
            await self._ws.send_str(msg)
            logger.info(f"Subscribed to quotes: {symbol}")

    async def subscribe_dom(self, symbol: str):
        """Subscribe to depth-of-market data."""
        if self._ws:
            self._request_id += 1
            msg = f"md/subscribeDOM\n{self._request_id}\n\n{{\"symbol\":\"{symbol}\"}}"
            await self._ws.send_str(msg)

    async def subscribe_chart(self, symbol: str, timeframe: str = "5min"):
        """Subscribe to chart/candle data.

        Timeframe options:
        - "1min", "5min", "15min", "30min", "1hour", "1day"
        """
        # Map timeframe to Tradovate chart description
        tf_map = {
            "1min": {"underlyingType": "MinuteBar", "elementSize": 1},
            "5min": {"underlyingType": "MinuteBar", "elementSize": 5},
            "15min": {"underlyingType": "MinuteBar", "elementSize": 15},
            "30min": {"underlyingType": "MinuteBar", "elementSize": 30},
            "1hour": {"underlyingType": "MinuteBar", "elementSize": 60},
            "1day": {"underlyingType": "DailyBar", "elementSize": 1},
        }

        desc = tf_map.get(timeframe, tf_map["5min"])

        if self._ws:
            self._request_id += 1
            payload = {
                "symbol": symbol,
                "chartDescription": {
                    **desc,
                    "elementSizeUnit": "UnderlyingUnits",
                    "withHistogram": False,
                },
                "timeRange": {
                    "asFarAsTimestamp": datetime.now().isoformat(),
                    "closestTimestamp": (datetime.now() - timedelta(days=1)).isoformat(),
                },
            }
            msg = f"md/getChart\n{self._request_id}\n\n{json.dumps(payload)}"
            await self._ws.send_str(msg)
            logger.info(f"Subscribed to chart: {symbol} {timeframe}")

    async def _handle_message(self, raw: str):
        """Parse and dispatch WebSocket messages."""
        # Tradovate WS messages format: type\nid\n\njson_body
        # or heartbeat frames
        if raw.startswith("o") or raw == "h" or raw.startswith("a"):
            return

        try:
            # Parse the message frames
            lines = raw.split("\n")
            if len(lines) < 3:
                return

            msg_type = lines[0]
            body = "\n".join(lines[3:]) if len(lines) > 3 else ""

            if body:
                data = json.loads(body)
            else:
                data = {}

            # Dispatch to callbacks
            if msg_type in self._callbacks:
                for cb in self._callbacks[msg_type]:
                    if asyncio.iscoroutinefunction(cb):
                        await cb(data)
                    else:
                        cb(data)

            # Generic quote handler
            if "quotes" in str(msg_type).lower() and "quote" in self._callbacks:
                for cb in self._callbacks["quote"]:
                    if asyncio.iscoroutinefunction(cb):
                        await cb(data)
                    else:
                        cb(data)

        except (json.JSONDecodeError, IndexError) as e:
            logger.debug(f"Could not parse WS message: {e}")


# ── Convenience Factory ──────────────────────────────────────────────────

class TradovateClient:
    """High-level Tradovate API client combining REST + WebSocket."""

    def __init__(self, config: Optional[TradovateConfig] = None):
        self.config = config or TradovateConfig.from_env()
        self.auth = TradovateAuth(self.config)
        self.rest = TradovateREST(self.config, self.auth)
        self.market_data = TradovateMarketData(self.config, self.auth)
        self._account_id: Optional[int] = None

    async def connect(self):
        """Authenticate and connect to WebSocket."""
        await self.auth.authenticate()
        accounts = await self.rest.get_accounts()
        if accounts:
            self._account_id = accounts[0].get("id")
            logger.info(f"Using account: {self._account_id}")

    async def start_market_data(self, symbol: str = "MESM5"):
        """Start receiving real-time market data."""
        await self.market_data.connect()
        await self.market_data.subscribe_quotes(symbol)
        await self.market_data.subscribe_chart(symbol, "5min")

    async def place_market_order(self, action: str, symbol: str, qty: int = 1) -> Dict:
        """Place a market order (Buy/Sell)."""
        if not self._account_id:
            raise RuntimeError("Not connected. Call connect() first.")
        return await self.rest.place_order(
            account_id=self._account_id,
            action=action,
            symbol=symbol,
            order_qty=qty,
            order_type="Market",
        )

    async def flatten_all(self) -> Dict:
        """Emergency flatten all positions."""
        if not self._account_id:
            raise RuntimeError("Not connected. Call connect() first.")
        return await self.rest.flatten_position(self._account_id)
