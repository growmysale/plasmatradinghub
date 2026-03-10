"""Tradovate API Client for PropEdge.

Handles authentication, real-time WebSocket data, and order management.
TopstepX uses Tradovate as their execution platform.

Connection modes:
- Demo: https://demo.tradovateapi.com/v1 (free sandbox)
- Live: https://live.tradovateapi.com/v1 (real money)

Authentication: OAuth2 with device auth flow
WebSocket: Real-time market data + order updates

Tradovate WebSocket Protocol:
  Request format:  endpoint\nrequestId\n\njsonBody
  Response format: endpoint\nrequestId\nstatusLine\njsonBody

  WebSocket framing (SockJS-style):
    "o"       - connection open
    "h"       - heartbeat (respond with "[]")
    "a[...]"  - data frame (JSON array of protocol messages)
    "c[...]"  - connection close
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
        """Make an authenticated API request with auto token refresh."""
        url = f"{self.config.api_url}{endpoint}"

        for attempt in range(2):
            await self.auth.ensure_token()
            headers = self.auth.get_headers()

            try:
                async with aiohttp.ClientSession() as session:
                    if method == "GET":
                        async with session.get(url, headers=headers) as resp:
                            if resp.status == 401 and attempt == 0:
                                logger.info("Token expired, refreshing...")
                                self.auth.token = None  # Force re-auth
                                continue
                            resp_data = await resp.json()
                            if resp.status >= 400:
                                logger.error(
                                    f"API error {resp.status} {method} {endpoint}: "
                                    f"{resp_data}"
                                )
                            return resp_data
                    elif method == "POST":
                        async with session.post(url, headers=headers, json=data) as resp:
                            if resp.status == 401 and attempt == 0:
                                logger.info("Token expired, refreshing...")
                                self.auth.token = None
                                continue
                            resp_data = await resp.json()
                            if resp.status >= 400:
                                logger.error(
                                    f"API error {resp.status} {method} {endpoint}: "
                                    f"{resp_data}"
                                )
                            return resp_data
            except aiohttp.ClientError as e:
                logger.error(f"HTTP request error {method} {endpoint}: {e}")
                if attempt == 0:
                    continue
                raise

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
        symbol: str,         # e.g., "MESM6" (MES June 2026)
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

    async def place_oso(
        self,
        account_id: int,
        action: str,
        symbol: str,
        order_qty: int,
        order_type: str = "Market",
        price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> Dict:
        """Place an order with attached bracket (OSO — Order Sends Order).

        Places entry order with stop-loss and take-profit brackets.
        This is essential for proper risk management in live trading.
        """
        # Build the entry order
        entry = {
            "accountSpec": self.config.username,
            "accountId": account_id,
            "action": action,
            "symbol": symbol,
            "orderQty": order_qty,
            "orderType": order_type,
            "timeInForce": "Day",
        }
        if price is not None:
            entry["price"] = price

        # Build bracket orders (reverse action for exit)
        exit_action = "Sell" if action == "Buy" else "Buy"
        brackets = []

        if stop_loss is not None:
            brackets.append({
                "action": exit_action,
                "orderType": "Stop",
                "stopPrice": stop_loss,
            })

        if take_profit is not None:
            brackets.append({
                "action": exit_action,
                "orderType": "Limit",
                "price": take_profit,
            })

        payload = {
            "accountSpec": self.config.username,
            "accountId": account_id,
            "action": action,
            "symbol": symbol,
            "orderQty": order_qty,
            "orderType": order_type,
            "timeInForce": "Day",
        }
        if price is not None:
            payload["price"] = price

        if brackets:
            payload["bracket1"] = brackets[0] if len(brackets) > 0 else None
            payload["bracket2"] = brackets[1] if len(brackets) > 1 else None

        return await self._request("POST", "/order/placeOSO", payload)

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
        """Find a contract by symbol name (e.g., 'MESM6')."""
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
    - Chart/candle data streaming (with historical backfill)

    Features:
    - Proper SockJS frame parsing (o/h/a/c frames)
    - Automatic heartbeat responses
    - Reconnection with exponential backoff
    - Subscription tracking with auto-resubscribe on reconnect
    - Connection health monitoring
    """

    MAX_RECONNECT_ATTEMPTS = 10
    HEALTH_CHECK_INTERVAL = 30  # seconds
    STALE_CONNECTION_TIMEOUT = 90  # seconds

    def __init__(self, config: TradovateConfig, auth: TradovateAuth):
        self.config = config
        self.auth = auth
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._callbacks: Dict[str, List[Callable]] = {}
        self._running = False
        self._request_id = 0

        # Connection state
        self._last_msg_time: float = 0.0
        self._authorized = False
        self._reconnect_count = 0

        # Subscription tracking (for auto-resubscribe after reconnect)
        self._subscriptions: List[Dict[str, str]] = []

    def _next_id(self) -> int:
        """Get next request ID for the Tradovate protocol."""
        self._request_id += 1
        return self._request_id

    def on(self, event: str, callback: Callable):
        """Register a callback for a market data event (idempotent).

        Events:
        - "chart"  : Chart bar data received
        - "quote"  : Real-time quote (bid/ask/last)
        - "dom"    : Depth of market update
        - "_connected" : WebSocket connected (internal)
        - "_disconnected" : WebSocket disconnected (internal)
        """
        if event not in self._callbacks:
            self._callbacks[event] = []
        if callback not in self._callbacks[event]:
            self._callbacks[event].append(callback)

    # ── Connection ───────────────────────────────────────────

    async def connect(self):
        """Connect to Tradovate MD WebSocket with auto-reconnection.

        This method blocks in the message loop. It automatically reconnects
        on disconnection with exponential backoff. Subscriptions are restored
        after each reconnect.
        """
        self._running = True
        self._reconnect_count = 0

        while self._running:
            try:
                token = await self.auth.ensure_token()
                self._last_msg_time = time.time()
                self._authorized = False

                async with aiohttp.ClientSession() as session:
                    logger.info(
                        f"Connecting to Tradovate MD WebSocket: {self.config.md_url}"
                    )
                    async with session.ws_connect(
                        self.config.md_url,
                        heartbeat=30.0,
                        timeout=aiohttp.ClientWSTimeout(ws_close=10.0),
                    ) as ws:
                        self._ws = ws
                        self._reconnect_count = 0  # Reset on successful connect

                        # Authorize the WebSocket connection
                        auth_msg = f"authorize\n{self._next_id()}\n\n{token}"
                        await ws.send_str(auth_msg)
                        logger.info("Sent authorization to Tradovate MD WebSocket")

                        # Allow time for auth processing, then resubscribe
                        await asyncio.sleep(2)
                        self._authorized = True

                        # Restore all subscriptions (e.g., after reconnect)
                        await self._resubscribe_all()

                        await self._emit_async("_connected", {
                            "reconnect_count": self._reconnect_count,
                        })

                        logger.info(
                            f"Tradovate MD WebSocket ready "
                            f"({len(self._subscriptions)} subscriptions)"
                        )

                        # Start connection health monitor
                        health_task = asyncio.create_task(
                            self._health_monitor()
                        )

                        try:
                            async for msg in ws:
                                if not self._running:
                                    break

                                if msg.type == aiohttp.WSMsgType.TEXT:
                                    await self._handle_message(msg.data)
                                elif msg.type in (
                                    aiohttp.WSMsgType.CLOSED,
                                    aiohttp.WSMsgType.CLOSING,
                                ):
                                    logger.warning(
                                        "Tradovate WS closed by server"
                                    )
                                    break
                                elif msg.type == aiohttp.WSMsgType.ERROR:
                                    logger.error(
                                        f"Tradovate WS error: {ws.exception()}"
                                    )
                                    break
                        finally:
                            health_task.cancel()
                            try:
                                await health_task
                            except asyncio.CancelledError:
                                pass

            except asyncio.CancelledError:
                logger.info("Tradovate WS connection cancelled")
                self._running = False
                raise

            except Exception as e:
                logger.error(f"Tradovate WS connection error: {e}")

            # ── Reconnection logic ───────────────────────────────
            if not self._running:
                break

            self._reconnect_count += 1
            if self._reconnect_count > self.MAX_RECONNECT_ATTEMPTS:
                logger.error(
                    f"Max reconnect attempts ({self.MAX_RECONNECT_ATTEMPTS}) "
                    f"exceeded. Giving up."
                )
                self._running = False
                await self._emit_async("_disconnected", {
                    "reason": "max_reconnects_exceeded",
                })
                break

            delay = min(
                5 * (2 ** (self._reconnect_count - 1)),
                300,  # Cap at 5 minutes
            )
            logger.info(
                f"Reconnecting Tradovate WS in {delay}s "
                f"(attempt {self._reconnect_count}/{self.MAX_RECONNECT_ATTEMPTS})"
            )
            await asyncio.sleep(delay)

        self._ws = None
        self._authorized = False

    async def disconnect(self):
        """Disconnect from WebSocket gracefully."""
        self._running = False
        if self._ws and not self._ws.closed:
            try:
                await self._ws.close()
            except Exception as e:
                logger.debug(f"Error closing WS: {e}")
        self._ws = None
        self._authorized = False

    # ── Subscriptions ────────────────────────────────────────

    async def subscribe_quotes(self, symbol: str):
        """Subscribe to real-time quotes for a symbol.

        Queues the subscription if not yet connected. Subscriptions are
        automatically restored after reconnection.
        """
        sub = {"type": "quote", "symbol": symbol}
        if sub not in self._subscriptions:
            self._subscriptions.append(sub)
        if self._ws and not self._ws.closed and self._authorized:
            await self._send_quote_sub(symbol)

    async def subscribe_dom(self, symbol: str):
        """Subscribe to depth-of-market data."""
        sub = {"type": "dom", "symbol": symbol}
        if sub not in self._subscriptions:
            self._subscriptions.append(sub)
        if self._ws and not self._ws.closed and self._authorized:
            await self._send_dom_sub(symbol)

    async def subscribe_chart(self, symbol: str, timeframe: str = "5min"):
        """Subscribe to chart/candle data.

        Requests last 200 bars of history, then streams real-time updates.
        Queues the subscription if not yet connected.

        Timeframe options: "1min", "5min", "15min", "30min", "1hour", "1day"
        """
        sub = {"type": "chart", "symbol": symbol, "timeframe": timeframe}
        if sub not in self._subscriptions:
            self._subscriptions.append(sub)
        if self._ws and not self._ws.closed and self._authorized:
            await self._send_chart_sub(symbol, timeframe)

    async def _resubscribe_all(self):
        """Resend all tracked subscriptions (e.g., after reconnect)."""
        if not self._subscriptions:
            return

        logger.info(
            f"Resubscribing to {len(self._subscriptions)} data feeds..."
        )
        for sub in list(self._subscriptions):
            try:
                if sub["type"] == "chart":
                    await self._send_chart_sub(
                        sub["symbol"], sub.get("timeframe", "5min")
                    )
                elif sub["type"] == "quote":
                    await self._send_quote_sub(sub["symbol"])
                elif sub["type"] == "dom":
                    await self._send_dom_sub(sub["symbol"])
            except Exception as e:
                logger.error(f"Resubscribe error for {sub}: {e}")

    async def _send_chart_sub(self, symbol: str, timeframe: str = "5min"):
        """Send chart subscription message to Tradovate."""
        tf_map = {
            "1min": {"underlyingType": "MinuteBar", "elementSize": 1},
            "5min": {"underlyingType": "MinuteBar", "elementSize": 5},
            "15min": {"underlyingType": "MinuteBar", "elementSize": 15},
            "30min": {"underlyingType": "MinuteBar", "elementSize": 30},
            "1hour": {"underlyingType": "MinuteBar", "elementSize": 60},
            "1day": {"underlyingType": "DailyBar", "elementSize": 1},
        }
        desc = tf_map.get(timeframe, tf_map["5min"])

        req_id = self._next_id()
        payload = {
            "symbol": symbol,
            "chartDescription": {
                **desc,
                "elementSizeUnit": "UnderlyingUnits",
                "withHistogram": False,
            },
            "timeRange": {
                "asMuchAsElements": 200,
            },
        }
        msg = f"md/getChart\n{req_id}\n\n{json.dumps(payload)}"
        await self._ws.send_str(msg)
        logger.info(
            f"Chart subscription sent: {symbol} {timeframe} (req={req_id})"
        )

    async def _send_quote_sub(self, symbol: str):
        """Send quote subscription message to Tradovate."""
        req_id = self._next_id()
        payload = json.dumps({"symbol": symbol})
        msg = f"md/subscribeQuote\n{req_id}\n\n{payload}"
        await self._ws.send_str(msg)
        logger.info(f"Quote subscription sent: {symbol} (req={req_id})")

    async def _send_dom_sub(self, symbol: str):
        """Send DOM subscription message to Tradovate."""
        req_id = self._next_id()
        payload = json.dumps({"symbol": symbol})
        msg = f"md/subscribeDOM\n{req_id}\n\n{payload}"
        await self._ws.send_str(msg)
        logger.info(f"DOM subscription sent: {symbol} (req={req_id})")

    # ── Message Handling ─────────────────────────────────────

    async def _handle_message(self, raw: str):
        """Parse and dispatch WebSocket messages.

        Tradovate uses SockJS-style framing:
        - "o"       : Connection opened
        - "h"       : Heartbeat from server (respond with "[]")
        - "a[...]"  : Data frame — JSON array of Tradovate protocol messages
        - "c[...]"  : Connection close (with code and reason)

        Inside "a" frames, each message follows the Tradovate protocol:
          endpoint\nrequestId\n(statusLine)\njsonBody
        """
        if not raw:
            return

        self._last_msg_time = time.time()

        # ── SockJS open frame ────────────────────────────────
        if raw == "o":
            logger.info("Tradovate WS: SockJS connection established")
            return

        # ── SockJS heartbeat ─────────────────────────────────
        if raw == "h":
            # Respond to server heartbeat to keep connection alive
            if self._ws and not self._ws.closed:
                try:
                    await self._ws.send_str("[]")
                except Exception as e:
                    logger.warning(f"Failed to send heartbeat response: {e}")
            return

        # ── SockJS close frame ───────────────────────────────
        if raw.startswith("c"):
            logger.warning(f"Tradovate WS: server close frame: {raw}")
            # Don't set _running=False here — let the reconnect logic handle it
            return

        # ── SockJS data frame ────────────────────────────────
        if raw.startswith("a"):
            try:
                # Parse the JSON array that follows "a"
                messages = json.loads(raw[1:])
                for msg_str in messages:
                    await self._process_tradovate_message(msg_str)
            except json.JSONDecodeError as e:
                logger.warning(
                    f"Failed to parse SockJS data frame: {e} "
                    f"(raw={raw[:200]})"
                )
            return

        # ── Not SockJS-wrapped — process directly ────────────
        await self._process_tradovate_message(raw)

    async def _process_tradovate_message(self, msg: str):
        """Process a single Tradovate protocol message.

        Tradovate protocol format:
          endpoint\nrequestId\n(statusLine)\njsonBody

        Examples:
          md/getChart\n3\ns\n200\n{"charts":[...]}
          md/subscribeQuote\n4\ns\n200\n{...}
          chart\n\n\n{"charts":[{...}]}    (pushed event)
        """
        try:
            # Split into at most 4 parts
            parts = msg.split("\n", 3)

            if not parts or not parts[0].strip():
                return

            endpoint = parts[0].strip()
            request_id = parts[1].strip() if len(parts) > 1 else ""

            # Find the JSON body — may be at different positions
            body_str = ""
            if len(parts) == 4:
                body_str = parts[3]
            elif len(parts) == 3:
                candidate = parts[2].strip()
                if candidate.startswith("{") or candidate.startswith("["):
                    body_str = candidate
                # else it's a status line with no body
            elif len(parts) == 2:
                candidate = parts[1].strip()
                if candidate.startswith("{") or candidate.startswith("["):
                    body_str = candidate

            data: Dict[str, Any] = {}
            if body_str.strip():
                try:
                    data = json.loads(body_str)
                except json.JSONDecodeError:
                    # Some messages have non-JSON status info — ignore
                    pass

            logger.debug(
                f"Tradovate msg: {endpoint} (id={request_id}, "
                f"keys={list(data.keys()) if data else []})"
            )

            # ── Route to specific handlers ───────────────────

            # Chart data: endpoint contains "chart" or data has "charts" key
            if "chart" in endpoint.lower() or "charts" in data:
                charts = data.get("charts", [])
                for chart in charts:
                    bars = chart.get("bars", [])
                    if bars:
                        chart_data = {
                            "charts": [{
                                "id": chart.get("id"),
                                "td": chart.get("td"),
                                "bars": bars,
                            }],
                            "eoh": chart.get("eoh", False),
                        }
                        await self._emit_async("chart", chart_data)

            # Quote data
            if "quote" in endpoint.lower() or "quotes" in data:
                quotes = data.get("quotes", [])
                if not quotes and "entries" in data:
                    quotes = [data]  # Some formats nest differently
                for quote in quotes:
                    await self._emit_async("quote", quote)

            # DOM data
            if "dom" in endpoint.lower() or "doms" in data:
                await self._emit_async("dom", data)

            # Generic endpoint callback (e.g., for "authorize" responses)
            await self._emit_async(endpoint, data)

        except Exception as e:
            logger.debug(
                f"Error processing Tradovate message: {e}, "
                f"msg={msg[:200]}"
            )

    async def _emit_async(self, event: str, data: Any):
        """Dispatch event to registered callbacks."""
        callbacks = self._callbacks.get(event, [])
        for cb in callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(data)
                else:
                    cb(data)
            except Exception as e:
                logger.error(f"Callback error for '{event}': {e}")

    # ── Health Monitoring ────────────────────────────────────

    async def _health_monitor(self):
        """Monitor connection health and detect stale connections.

        Runs as a background task alongside the main message loop.
        Sends keepalive pings if no messages received recently.
        """
        while self._running:
            await asyncio.sleep(self.HEALTH_CHECK_INTERVAL)

            elapsed = time.time() - self._last_msg_time
            if elapsed > self.STALE_CONNECTION_TIMEOUT:
                logger.warning(
                    f"No messages for {elapsed:.0f}s — connection may be stale"
                )
                if self._ws and not self._ws.closed:
                    try:
                        # Send empty array as keepalive
                        await self._ws.send_str("[]")
                    except Exception:
                        logger.error(
                            "Failed to send keepalive. "
                            "Closing stale connection for reconnect."
                        )
                        try:
                            await self._ws.close()
                        except Exception:
                            pass
                        break


# ── Convenience Factory ──────────────────────────────────────────────────

class TradovateClient:
    """High-level Tradovate API client combining REST + WebSocket.

    Usage:
        client = TradovateClient()
        await client.connect()  # Authenticates + fetches account

        # Register callbacks for market data events
        client.market_data.on("chart", on_chart_callback)

        # Queue subscriptions (sent when WS connects)
        await client.market_data.subscribe_chart("MESH6", "5min")

        # Start WebSocket (blocks in message loop with auto-reconnect)
        await client.market_data.connect()
    """

    def __init__(self, config: Optional[TradovateConfig] = None):
        self.config = config or TradovateConfig.from_env()
        self.auth = TradovateAuth(self.config)
        self.rest = TradovateREST(self.config, self.auth)
        self.market_data = TradovateMarketData(self.config, self.auth)
        self._account_id: Optional[int] = None

    async def connect(self):
        """Authenticate and fetch account info (does NOT start WebSocket)."""
        await self.auth.authenticate()
        accounts = await self.rest.get_accounts()
        if accounts:
            self._account_id = accounts[0].get("id")
            logger.info(f"Using account: {self._account_id}")
        else:
            logger.warning("No trading accounts found")

    async def start_market_data(self, symbol: str = ""):
        """Start receiving real-time market data (blocks in WS loop).

        If no symbol provided, resolves the current front-month contract.
        """
        if not symbol:
            from orchestrator.contract_resolver import ContractResolver
            symbol = ContractResolver().get_front_month()

        await self.market_data.subscribe_quotes(symbol)
        await self.market_data.subscribe_chart(symbol, "5min")
        await self.market_data.connect()

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

    async def place_bracket_order(
        self,
        action: str,
        symbol: str,
        qty: int = 1,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> Dict:
        """Place a market order with SL/TP brackets (OSO order)."""
        if not self._account_id:
            raise RuntimeError("Not connected. Call connect() first.")
        return await self.rest.place_oso(
            account_id=self._account_id,
            action=action,
            symbol=symbol,
            order_qty=qty,
            order_type="Market",
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

    async def flatten_all(self) -> Dict:
        """Emergency flatten all positions."""
        if not self._account_id:
            raise RuntimeError("Not connected. Call connect() first.")
        return await self.rest.flatten_position(self._account_id)
