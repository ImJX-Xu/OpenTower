"""Webhook Channel — HTTP API for programmatic access.

Exposes a simple POST endpoint for sending messages to the agent
and receiving responses. Useful for integrations with other systems.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator

from opentower.channels import Channel, Message

logger = logging.getLogger("opentower.channels.webhook")


class WebhookChannel(Channel):
    """HTTP webhook channel using aiohttp."""

    def __init__(self, port: int = 8080) -> None:
        self.port = port
        self._queue: asyncio.Queue[Message] = asyncio.Queue()
        self._response_waiters: dict[str, asyncio.Future] = {}
        self._app = None
        self._runner = None

    async def start(self) -> None:
        """Start the HTTP server."""
        try:
            from aiohttp import web

            self._app = web.Application()
            self._app.router.add_post("/message", self._handle_message)
            self._app.router.add_get("/health", self._handle_health)

            self._runner = web.AppRunner(self._app)
            await self._runner.setup()
            site = web.TCPSite(self._runner, "0.0.0.0", self.port)
            await site.start()
            logger.info("Webhook listening on port %d", self.port)
        except ImportError:
            logger.warning("aiohttp not installed — webhook channel disabled")

    async def listen(self) -> AsyncIterator[Message]:
        """Yield messages from the HTTP queue."""
        while True:
            msg = await self._queue.get()
            yield msg

    async def send(self, text: str) -> None:
        """Send response to the waiting HTTP request."""
        # Responses are sent back through the request handler
        pass

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()

    async def _handle_message(self, request):
        from aiohttp import web
        try:
            data = await request.json()
            text = data.get("message", data.get("text", ""))
            if not text:
                return web.json_response({"error": "No message"}, status=400)

            msg = Message(text=text, sender="webhook", channel="webhook")
            await self._queue.put(msg)
            return web.json_response({"status": "received"})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def _handle_health(self, request):
        from aiohttp import web
        return web.json_response({"status": "ok", "agent": "OpenTower"})
