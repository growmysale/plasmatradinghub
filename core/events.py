"""PropEdge Event Bus - Async pub/sub for inter-layer communication.

Every layer publishes and subscribes to events. All events are logged
for replay and analysis. This is the nervous system of the platform.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """All event types in the system."""

    # Market Events (from Data Engine)
    PRICE_UPDATE = "price_update"
    CANDLE_CLOSE = "candle_close"
    VOLUME_SPIKE = "volume_spike"
    NEWS_EVENT = "news_event"
    ECONOMIC_RELEASE = "economic_release"

    # Feature Events (from Feature Engine)
    FEATURES_UPDATED = "features_updated"
    REGIME_CHANGE = "regime_change"
    STRUCTURE_CHANGE = "structure_change"
    FVG_FORMED = "fvg_formed"
    ORDER_BLOCK = "order_block"

    # Signal Events (from Strategy Agents)
    AGENT_SIGNAL = "agent_signal"

    # Allocation Events (from Meta-Strategy)
    COMBINED_SIGNAL = "combined_signal"
    STRATEGY_PROMOTED = "strategy_promoted"
    STRATEGY_DEMOTED = "strategy_demoted"
    STRATEGY_KILLED = "strategy_killed"

    # Risk Events (from Risk Manager)
    ORDER_APPROVED = "order_approved"
    ORDER_REJECTED = "order_rejected"
    RISK_WARNING = "risk_warning"
    CIRCUIT_BREAKER = "circuit_breaker"
    COMPLIANCE_UPDATE = "compliance_update"

    # Execution Events (from Execution Engine)
    ORDER_SUBMITTED = "order_submitted"
    ORDER_FILLED = "order_filled"
    POSITION_OPENED = "position_opened"
    POSITION_CLOSED = "position_closed"

    # System Events
    BACKTEST_COMPLETE = "backtest_complete"
    MODEL_RETRAINED = "model_retrained"
    DAILY_REPORT = "daily_report"
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    SYSTEM_ERROR = "system_error"


@dataclass
class Event:
    """Base event with metadata."""
    type: EventType
    data: Dict[str, Any] = field(default_factory=dict)
    ts: datetime = field(default_factory=datetime.now)
    source: str = ""

    def to_dict(self) -> dict:
        """Serialize for logging/storage."""
        d = {
            "type": self.type.value,
            "ts": self.ts.isoformat(),
            "source": self.source,
            "data": _serialize(self.data),
        }
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)


def _serialize(obj: Any) -> Any:
    """Recursively serialize objects for JSON."""
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, datetime):
        return obj.isoformat()
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: _serialize(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialize(i) for i in obj]
    return obj


# Type alias for event handlers
EventHandler = Callable[[Event], Coroutine[Any, Any, None]]


class EventBus:
    """Async event bus with pub/sub pattern.

    Usage:
        bus = EventBus()

        # Subscribe
        async def on_candle(event: Event):
            print(event.data)
        bus.subscribe(EventType.CANDLE_CLOSE, on_candle)

        # Publish
        await bus.publish(Event(
            type=EventType.CANDLE_CLOSE,
            data={"symbol": "MES", "close": 5847.50},
            source="data_engine"
        ))
    """

    def __init__(self, log_events: bool = True):
        self._subscribers: Dict[EventType, List[EventHandler]] = defaultdict(list)
        self._global_subscribers: List[EventHandler] = []
        self._event_log: List[Event] = []
        self._log_events = log_events
        self._running = False
        self._queue: asyncio.Queue[Event] = asyncio.Queue()
        self._stats: Dict[str, int] = defaultdict(int)

    def subscribe(self, event_type: EventType, handler: EventHandler):
        """Subscribe to a specific event type."""
        self._subscribers[event_type].append(handler)
        logger.debug(f"Subscribed {handler.__qualname__} to {event_type.value}")

    def subscribe_all(self, handler: EventHandler):
        """Subscribe to ALL events (for logging, debugging)."""
        self._global_subscribers.append(handler)

    def unsubscribe(self, event_type: EventType, handler: EventHandler):
        """Remove a handler from an event type."""
        if handler in self._subscribers[event_type]:
            self._subscribers[event_type].remove(handler)

    async def publish(self, event: Event):
        """Publish an event to all subscribers."""
        if self._log_events:
            self._event_log.append(event)

        self._stats[event.type.value] += 1

        # Notify type-specific subscribers
        handlers = self._subscribers.get(event.type, []) + self._global_subscribers
        tasks = []
        for handler in handlers:
            try:
                tasks.append(asyncio.create_task(handler(event)))
            except Exception as e:
                logger.error(f"Error creating task for {handler.__qualname__}: {e}")

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(
                        f"Event handler error ({handlers[i].__qualname__}): {result}"
                    )

    async def publish_nowait(self, event: Event):
        """Queue event for async processing (non-blocking)."""
        await self._queue.put(event)

    async def start(self):
        """Start the event processing loop."""
        self._running = True
        logger.info("Event bus started")
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                await self.publish(event)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Event bus error: {e}")

    def stop(self):
        """Stop the event processing loop."""
        self._running = False
        logger.info("Event bus stopped")

    def get_event_log(
        self,
        event_type: Optional[EventType] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Event]:
        """Get logged events with optional filtering."""
        events = self._event_log
        if event_type:
            events = [e for e in events if e.type == event_type]
        if since:
            events = [e for e in events if e.ts >= since]
        return events[-limit:]

    def get_stats(self) -> Dict[str, int]:
        """Get event count statistics."""
        return dict(self._stats)

    def clear_log(self):
        """Clear the event log (for memory management)."""
        self._event_log.clear()


# Global event bus singleton
_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Get or create the global event bus."""
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus
