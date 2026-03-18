"""Scheduler — heartbeat loop + cron-based scheduled tasks.

The heartbeat makes the agent truly autonomous: it wakes up
periodically to check tasks, run schedules, and self-reflect.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable, Awaitable, Optional

logger = logging.getLogger("opentower.scheduler")


class Scheduler:
    """Heartbeat + scheduled task runner.

    Usage::

        scheduler = Scheduler(interval=300, on_wake=agent_wake_handler)
        scheduler.add_cron("0 9 * * *", agent_daily_review)
        await scheduler.start()
    """

    def __init__(
        self,
        interval: int = 300,
        on_wake: Optional[Callable[[], Awaitable[None]]] = None,
    ) -> None:
        self._interval = interval
        self._on_wake = on_wake
        self._schedules: list[dict] = []
        self._task: asyncio.Task | None = None
        self._running = False

    def add_schedule(self, cron_expr: str, action: str, handler: Callable) -> None:
        """Add a cron-style scheduled task."""
        self._schedules.append({
            "cron": cron_expr,
            "action": action,
            "handler": handler,
            "last_run": None,
        })
        logger.info("Scheduled: '%s' (%s)", action[:40], cron_expr)

    async def start(self) -> None:
        """Start the heartbeat loop."""
        self._running = True
        self._task = asyncio.create_task(self._heartbeat_loop())
        logger.info("Scheduler started (heartbeat=%ds)", self._interval)

    async def stop(self) -> None:
        """Stop the heartbeat loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Scheduler stopped")

    async def _heartbeat_loop(self) -> None:
        """Core heartbeat — wake up periodically and do work."""
        while self._running:
            try:
                await asyncio.sleep(self._interval)

                now = datetime.now(timezone.utc)
                logger.debug("Heartbeat at %s", now.isoformat())

                # Run on_wake callback
                if self._on_wake:
                    try:
                        await self._on_wake()
                    except Exception:
                        logger.exception("on_wake handler failed")

                # Check cron schedules
                for sched in self._schedules:
                    if self._should_run(sched, now):
                        logger.info("Running scheduled: %s", sched["action"][:40])
                        sched["last_run"] = now
                        try:
                            await sched["handler"](sched["action"])
                        except Exception:
                            logger.exception("Scheduled task failed: %s", sched["action"][:40])

            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Heartbeat error")

    @staticmethod
    def _should_run(sched: dict, now: datetime) -> bool:
        """Simple cron check — supports minute-level granularity.

        Supports: "*/N * * * *" (every N minutes) and "M H * * *" (at H:M).
        """
        cron = sched["cron"]
        last = sched.get("last_run")

        # Don't run twice in the same minute
        if last and last.minute == now.minute and last.hour == now.hour:
            return False

        parts = cron.split()
        if len(parts) < 5:
            return False

        minute_part, hour_part = parts[0], parts[1]

        # Every N minutes: */N
        if minute_part.startswith("*/"):
            try:
                n = int(minute_part[2:])
                return now.minute % n == 0
            except ValueError:
                return False

        # Exact minute + hour
        try:
            target_min = int(minute_part)
            if hour_part == "*":
                return now.minute == target_min
            target_hour = int(hour_part)
            return now.minute == target_min and now.hour == target_hour
        except ValueError:
            return False
