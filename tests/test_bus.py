"""Tests for event bus (unchanged from V1.0)."""

import asyncio
import pytest

from opentower.bus.event_bus import EMPBus
from opentower.schema.emp import EMPPacket


@pytest.mark.asyncio
async def test_subscribe_and_publish():
    bus = EMPBus()
    received = []

    async def handler(pkt):
        received.append(pkt)

    bus.subscribe("test_intent", handler)
    await bus.start()

    pkt = EMPPacket(source="a", intent_type="test_intent", action="hello", token_budget=100)
    await bus.publish(pkt)
    await asyncio.sleep(0.1)

    assert len(received) == 1
    assert received[0].action == "hello"
    await bus.stop()


@pytest.mark.asyncio
async def test_no_subscriber():
    bus = EMPBus()
    await bus.start()
    pkt = EMPPacket(source="a", intent_type="no_one", action="lost", token_budget=100)
    await bus.publish(pkt)  # should not raise
    await asyncio.sleep(0.1)
    await bus.stop()


@pytest.mark.asyncio
async def test_multiple_subscribers():
    bus = EMPBus()
    a, b = [], []

    async def ha(pkt): a.append(pkt)
    async def hb(pkt): b.append(pkt)

    bus.subscribe("multi", ha)
    bus.subscribe("multi", hb)
    await bus.start()

    await bus.publish(EMPPacket(source="x", intent_type="multi", action="go", token_budget=100))
    await asyncio.sleep(0.1)

    assert len(a) == 1
    assert len(b) == 1
    await bus.stop()


@pytest.mark.asyncio
async def test_ordering():
    bus = EMPBus()
    order = []

    async def handler(pkt):
        order.append(pkt.action)

    bus.subscribe("ordered", handler)
    await bus.start()

    for i in range(5):
        await bus.publish(EMPPacket(source="x", intent_type="ordered", action=str(i), token_budget=100))
    await asyncio.sleep(0.3)

    assert order == ["0", "1", "2", "3", "4"]
    await bus.stop()
