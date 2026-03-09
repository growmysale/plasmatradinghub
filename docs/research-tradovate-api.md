# Tradovate API Research

## Base URLs

| Service | Demo | Live |
|---|---|---|
| REST API | `https://demo.tradovateapi.com/v1` | `https://live.tradovateapi.com/v1` |
| Trading WebSocket | `wss://demo.tradovateapi.com/v1/websocket` | `wss://live.tradovateapi.com/v1/websocket` |
| Market Data WebSocket | `wss://md-demo.tradovateapi.com/v1/websocket` | `wss://md.tradovateapi.com/v1/websocket` |

**Important:** Trading WS and Market Data WS are SEPARATE connections.

## Auth Flow

POST `/auth/accesstokenrequest` with: `name`, `password`, `appId`, `appVersion`, `cid`, `sec`

Returns: `accessToken` (trading) + `mdAccessToken` (market data)
Tokens expire after 90 minutes. Refresh at 85 min via `GET /auth/renewaccesstoken`.

## WebSocket Protocol

- Frame types: `o` (open), `h` (heartbeat), `a[...]` (data), `c` (close)
- Client must send heartbeat `[]` every 2.5 seconds
- Request format: `endpoint\nrequestId\n\nbody`
- Response format: `{"i": requestId, "s": statusCode, "d": data}`

## CRITICAL: TopstepX Uses ProjectX API

TopstepX migrated away from Tradovate API to ProjectX API.
- ProjectX dashboard: `dashboard.projectx.com`
- Cost: ~$14.50/month
- Prop firm accounts on Tradovate return EMPTY data via Tradovate API
- Need ProjectX integration for TopstepX users

## Demo Environment

- Free to use, identical API surface to live
- API Access add-on ($25/month) required for live
- Minimum $1,000 for live funded account
