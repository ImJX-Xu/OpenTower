"""Layer 5: Action Registry — map action_type strings to callables.

Every concrete action (shell, GitHub, email, hardware …) registers itself
here.  The Worker agent looks up the registry to execute a task.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

logger = logging.getLogger("opentower.actions")

ActionHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class ActionRegistry:
    """Central action dispatch table.

    Usage::

        registry = ActionRegistry()

        @registry.register("shell_execute")
        async def run_shell(payload):
            ...

        result = await registry.execute("shell_execute", {"command": "dir"})
    """

    def __init__(self) -> None:
        self._handlers: dict[str, ActionHandler] = {}

    def register(self, name: str) -> Callable[[ActionHandler], ActionHandler]:
        """Decorator that registers an action handler under *name*."""

        def decorator(fn: ActionHandler) -> ActionHandler:
            self._handlers[name] = fn
            logger.info("Registered action: %s → %s", name, fn.__qualname__)
            return fn

        return decorator

    async def execute(self, action_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Look up and execute the action.

        Returns:
            The result dict from the handler.

        Raises:
            KeyError: If no handler is registered for *action_type*.
        """
        handler = self._handlers.get(action_type)
        if handler is None:
            available = ", ".join(sorted(self._handlers)) or "(none)"
            raise KeyError(
                f"Unknown action_type '{action_type}'. Available: {available}"
            )
        logger.info("Executing action: %s", action_type)
        return await handler(payload)

    @property
    def available_actions(self) -> list[str]:
        """List of registered action type names."""
        return sorted(self._handlers)
