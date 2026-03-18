"""Tests for Layer 2 (EMP event bus)."""

import asyncio
import pytest
import pytest_asyncio

from opentower.bus.event_bus import EMPBus
from opentower.schema.emp import EMPPacket


@pytest_asyncio.fixture
async def bus():
    b = EMPBus()
    await b.start()
    yield b
    await b.stop()


@pytest.mark.asyncio
async def test_subscribe_and_publish(bus: EMPBus):
    received: list[EMPPacket] = []

    async def handler(pkt: EMPPacket) -> None:
        received.append(pkt)

    bus.subscribe("test_intent", handler)

    pkt = EMPPacket(source="a", intent_type="test_intent", action="hello")
    await bus.publish(pkt)

    # Give the dispatch loop time to process
    await asyncio.sleep(0.1)

    assert len(received) == 1
    assert received[0].action == "hello"


@pytest.mark.asyncio
async def test_no_subscriber_no_crash(bus: EMPBus):
    """Publishing to an intent with no subscribers should not raise."""
    pkt = EMPPacket(source="a", intent_type="nonexistent", action="ignored")
    await bus.publish(pkt)
    await asyncio.sleep(0.1)
    # No assertion — just checking no exception


@pytest.mark.asyncio
async def test_multiple_subscribers(bus: EMPBus):
    results_a: list[str] = []
    results_b: list[str] = []

    async def handler_a(pkt: EMPPacket) -> None:
        results_a.append(pkt.action)

    async def handler_b(pkt: EMPPacket) -> None:
        results_b.append(pkt.action)

    bus.subscribe("multi", handler_a)
    bus.subscribe("multi", handler_b)

    await bus.publish(EMPPacket(source="x", intent_type="multi", action="ping"))
    await asyncio.sleep(0.1)

    assert results_a == ["ping"]
    assert results_b == ["ping"]


@pytest.mark.asyncio
async def test_message_ordering(bus: EMPBus):
    received: list[int] = []

    async def handler(pkt: EMPPacket) -> None:
        received.append(pkt.payload.get("seq", -1))

    bus.subscribe("ordered", handler)

    for i in range(5):
        await bus.publish(
            EMPPacket(source="x", intent_type="ordered", action=f"msg-{i}", payload={"seq": i})
        )

    await asyncio.sleep(0.3)
    assert received == [0, 1, 2, 3, 4]
