"""Feishu (Lark) Channel — 飞书机器人适配器.

Connects to Feishu/Lark Bot API as an event-driven channel.
Receives messages via webhook callback, sends replies via API.

中国企业 Agent 落地第一站: Hub 使用量 318k+.

Setup:
    1. Create a Feishu Bot in developer console
    2. Set Event Subscription URL to http://your-host:port/feishu/event
    3. Configure FEISHU_APP_ID, FEISHU_APP_SECRET in env or config

Usage::

    channel = FeishuChannel(app_id="...", app_secret="...", port=9000)
    await channel.start()
    async for msg in channel.listen():
        response = await agent.run(msg.text)
        await channel.send(response)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from typing import AsyncIterator, Optional

import httpx

from opentower.channels import Channel, Message

logger = logging.getLogger("opentower.channels.feishu")

_FEISHU_API = "https://open.feishu.cn/open-apis"


class FeishuChannel(Channel):
    """Feishu/Lark bot channel with event subscription + message API."""

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        *,
        verification_token: str = "",
        encrypt_key: str = "",
        port: int = 9000,
    ) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.verification_token = verification_token
        self.encrypt_key = encrypt_key
        self.port = port

        self._queue: asyncio.Queue[Message] = asyncio.Queue()
        self._reply_map: dict[str, str] = {}  # message_id → chat_id
        self._tenant_token: Optional[str] = None
        self._token_expires: float = 0
        self._runner = None

    async def start(self) -> None:
        """Start the Feishu event webhook server."""
        try:
            from aiohttp import web

            app = web.Application()
            app.router.add_post("/feishu/event", self._handle_event)
            app.router.add_get("/health", self._health)

            self._runner = web.AppRunner(app)
            await self._runner.setup()
            site = web.TCPSite(self._runner, "0.0.0.0", self.port)
            await site.start()
            logger.info("Feishu channel listening on port %d", self.port)

        except ImportError:
            logger.error("aiohttp required for Feishu channel: pip install aiohttp")

    async def listen(self) -> AsyncIterator[Message]:
        """Yield messages from Feishu events."""
        while True:
            msg = await self._queue.get()
            yield msg

    async def send(self, text: str, *, chat_id: str = "") -> None:
        """Send a message to a Feishu chat."""
        if not chat_id and self._reply_map:
            # Use the most recent chat_id
            chat_id = list(self._reply_map.values())[-1]

        if not chat_id:
            logger.warning("No chat_id to reply to")
            return

        token = await self._get_tenant_token()
        if not token:
            logger.error("Failed to get Feishu tenant token")
            return

        url = f"{_FEISHU_API}/im/v1/messages"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        body = {
            "receive_id": chat_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        }

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    url, headers=headers, json=body,
                    params={"receive_id_type": "chat_id"},
                )
                data = resp.json()
                if data.get("code") != 0:
                    logger.error("Feishu send error: %s", data.get("msg", "unknown"))
        except Exception as e:
            logger.error("Feishu send failed: %s", e)

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()

    # ── Internal ──────────────────────────────────────────────

    async def _handle_event(self, request):
        """Handle incoming Feishu event webhook."""
        from aiohttp import web

        try:
            data = await request.json()

            # URL verification challenge
            if "challenge" in data:
                return web.json_response({"challenge": data["challenge"]})

            # Verification token check
            if self.verification_token:
                if data.get("token") != self.verification_token:
                    return web.json_response({"error": "invalid token"}, status=403)

            # Extract message event
            event = data.get("event", {})
            msg_type = event.get("message", {}).get("message_type", "")
            sender = event.get("sender", {}).get("sender_id", {}).get("user_id", "unknown")

            if msg_type == "text":
                content = json.loads(event["message"]["content"])
                text = content.get("text", "")
                chat_id = event["message"].get("chat_id", "")
                msg_id = event["message"].get("message_id", "")

                # Store chat_id for reply
                if msg_id and chat_id:
                    self._reply_map[msg_id] = chat_id

                msg = Message(
                    text=text,
                    sender=sender,
                    channel="feishu",
                    metadata={"chat_id": chat_id, "message_id": msg_id},
                )
                await self._queue.put(msg)

            return web.json_response({"ok": True})

        except Exception as e:
            logger.exception("Feishu event error")
            return web.json_response({"error": str(e)}, status=500)

    async def _get_tenant_token(self) -> Optional[str]:
        """Get or refresh the Feishu tenant access token."""
        if self._tenant_token and time.time() < self._token_expires:
            return self._tenant_token

        url = f"{_FEISHU_API}/auth/v3/tenant_access_token/internal"
        body = {"app_id": self.app_id, "app_secret": self.app_secret}

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, json=body)
                data = resp.json()
                if data.get("code") == 0:
                    self._tenant_token = data["tenant_access_token"]
                    self._token_expires = time.time() + data.get("expire", 7200) - 300
                    return self._tenant_token
                else:
                    logger.error("Feishu token error: %s", data.get("msg"))
                    return None
        except Exception as e:
            logger.error("Feishu token request failed: %s", e)
            return None

    async def _health(self, request):
        from aiohttp import web
        return web.json_response({"status": "ok", "channel": "feishu"})
