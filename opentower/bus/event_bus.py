"""Layer 2: EMP Event Bus — lightweight asyncio routing hub.

This is the *elevator shaft* of the Empire State Building: every EMP packet
published here is dispatched in milliseconds to the subscriber(s) registered
for its ``intent_type``.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Awaitable, Callable

from opentower.schema.emp import EMPPacket

logger = logging.getLogger("opentower.bus")

Handler = Callable[[EMPPacket], Awaitable[None]]


class EMPBus:
    """Pure-asyncio, in-process event bus.

    * Zero external dependencies (no Redis in MVP).
    * Messages are buffered in an ``asyncio.Queue`` to guarantee ordering.
    * Handlers are dispatched concurrently per intent_type.
    """

    def __init__(self, maxsize: int = 256) -> None:
        self._subscribers: dict[str, list[Handler]] = defaultdict(list)
        self._queue: asyncio.Queue[EMPPacket] = asyncio.Queue(maxsize=maxsize)
        self._running = False
        self._dispatch_task: asyncio.Task | None = None

    # ── Subscription ───────────────────────────────────────────────

    def subscribe(self, intent_type: str, handler: Handler) -> None:
        """Register *handler* for packets matching *intent_type*."""
        self._subscribers[intent_type].append(handler)
        logger.info("Subscribed %s → %s", intent_type, handler.__qualname__)

    # ── Publishing ─────────────────────────────────────────────────

    async def publish(self, packet: EMPPacket) -> None:
        """Enqueue a packet for dispatch."""
        await self._queue.put(packet)
        logger.debug("Published [%s] %s → %s", packet.trace_id, packet.intent_type, packet.action)

    # ── Lifecycle ──────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the background dispatch loop."""
        if self._running:
            return
        self._running = True
        self._dispatch_task = asyncio.create_task(self._dispatch_loop(), name="emp-bus")
        logger.info("EMPBus started")

    async def stop(self) -> None:
        """Gracefully stop the dispatch loop after draining the queue."""
        self._running = False
        if self._dispatch_task:
            # Push a sentinel so the loop wakes up
            await self._queue.put(None)  # type: ignore[arg-type]
            await self._dispatch_task
            self._dispatch_task = None
        logger.info("EMPBus stopped")

    # ── Internal ───────────────────────────────────────────────────

    async def _dispatch_loop(self) -> None:
        """Consume packets from the queue and fan-out to subscribers."""
        while self._running:
            packet = await self._queue.get()
            if packet is None:
                break  # sentinel
            handlers = self._subscribers.get(packet.intent_type, [])
            if not handlers:
                logger.warning("No subscribers for intent_type=%s", packet.intent_type)
                continue
            # Fan-out to all registered handlers concurrently
            results = await asyncio.gather(
                *(h(packet) for h in handlers),
                return_exceptions=True,
            )
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(
                        "Handler %s raised %s: %s",
                        handlers[i].__qualname__,
                        type(result).__name__,
                        result,
                    )

    async def drain(self) -> None:
        """Wait until the queue is empty (useful for testing)."""
        await self._queue.join()
