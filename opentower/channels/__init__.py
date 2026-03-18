"""Channel adapters — pluggable input/output interfaces.

Channels are how users interact with the agent.
Each channel implements listen() → messages, send() → delivery.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator


@dataclass
class Message:
    """A single message from/to a channel."""
    text: str
    sender: str = "user"
    channel: str = "unknown"
    metadata: dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class Channel(ABC):
    """Base interface for all channel adapters."""

    @abstractmethod
    async def listen(self) -> AsyncIterator[Message]:
        """Yield incoming messages from this channel."""
        ...

    @abstractmethod
    async def send(self, text: str) -> None:
        """Send a response through this channel."""
        ...

    async def start(self) -> None:
        """Optional: setup/connect."""
        pass

    async def stop(self) -> None:
        """Optional: teardown/disconnect."""
        pass
