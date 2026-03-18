"""HTTP API skill — generic HTTP requests for integrating any API.

The universal connector: GET/POST/PUT/DELETE any REST API.
Foundation for Feishu, DingTalk, WeChat Work, Slack, etc.
"""

from __future__ import annotations

import json
import logging

import httpx

from opentower.skills import skill

logger = logging.getLogger("opentower.skills.http_api")

_TIMEOUT = 15


@skill(
    "http_request",
    description="Make an HTTP request to any API endpoint (GET/POST/PUT/DELETE)",
    parameters='{"url": "string (required)", "method": "string (default: GET)", "headers": "dict (optional)", "body": "dict (optional, for POST/PUT)", "params": "dict (optional, query params)"}',
)
async def http_request(
    url: str = "",
    method: str = "GET",
    headers: dict = None,
    body: dict = None,
    params: dict = None,
) -> dict:
    """Make an HTTP request and return the response."""
    if not url:
        return {"error": "No URL provided"}

    method = method.upper()
    if method not in ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"):
        return {"error": f"Unsupported method: {method}"}

    logger.info("HTTP %s %s", method, url[:80])

    try:
        req_headers = {"User-Agent": "OpenTower/3.1"}
        if headers:
            req_headers.update(headers)

        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            if method in ("POST", "PUT", "PATCH") and body:
                req_headers.setdefault("Content-Type", "application/json")
                resp = await client.request(
                    method, url,
                    headers=req_headers,
                    json=body,
                    params=params,
                )
            else:
                resp = await client.request(
                    method, url,
                    headers=req_headers,
                    params=params,
                )

        # Parse response
        content_type = resp.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                response_body = resp.json()
            except Exception:
                response_body = resp.text[:5000]
        else:
            response_body = resp.text[:5000]

        return {
            "status_code": resp.status_code,
            "headers": dict(resp.headers),
            "body": response_body,
            "url": str(resp.url),
        }

    except httpx.ConnectError:
        return {"error": f"Connection failed: {url}"}
    except httpx.ReadTimeout:
        return {"error": f"Timeout after {_TIMEOUT}s"}
    except Exception as e:
        return {"error": str(e)[:300]}


@skill(
    "webhook_send",
    description="Send a message to a webhook URL (Slack, Discord, Feishu, etc.)",
    parameters='{"url": "string (required) — webhook URL", "message": "string (required) — message text"}',
)
async def webhook_send(url: str = "", message: str = "") -> dict:
    """Send a message to a webhook endpoint."""
    if not url or not message:
        return {"error": "url and message are required"}

    # Auto-detect format
    if "hooks.slack.com" in url or "discord" in url:
        payload = {"text": message}  # Slack format
    elif "feishu" in url or "larksuite" in url:
        payload = {"msg_type": "text", "content": {"text": message}}  # Feishu format
    elif "dingtalk" in url:
        payload = {"msgtype": "text", "text": {"content": message}}  # DingTalk format
    else:
        payload = {"message": message}  # Generic

    return await http_request(url=url, method="POST", body=payload)
