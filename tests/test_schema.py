"""Tests for Layer 1 (company.yaml) and Layer 3 (EMP protocol)."""

import pytest
from pathlib import Path
from pydantic import ValidationError

from opentower.schema.company import CompanyConfig, NodeConfig, EmpireInfo, load_company
from opentower.schema.emp import EMPPacket, INTENT_TASK_ASSIGN, INTENT_TASK_RESULT


# ── company.yaml parsing ──────────────────────────────────────────


def test_load_company_from_file():
    """Ensure company.yaml in the repo root parses correctly."""
    root = Path(__file__).resolve().parent.parent / "company.yaml"
    if not root.exists():
        pytest.skip("company.yaml not found at repo root")
    config = load_company(root)
    assert config.empire.name == "OpenTower-Alpha"
    assert "ceo" in config.nodes
    assert "worker" in config.nodes
    assert "qa" in config.nodes


def test_node_config_defaults():
    node = NodeConfig(role="test", prompt="test prompt")
    assert node.permissions == []
    assert node.token_budget == 4096


def test_company_config_validation():
    with pytest.raises(ValidationError):
        CompanyConfig(empire="not-valid", nodes={})  # type: ignore[arg-type]


# ── EMP packet ─────────────────────────────────────────────────────


def test_emp_packet_creation():
    pkt = EMPPacket(
        source="ceo",
        target="worker",
        intent_type=INTENT_TASK_ASSIGN,
        action="list files",
        payload={"command": "dir"},
        token_budget=1000,
    )
    assert pkt.trace_id  # auto-generated
    assert pkt.source == "ceo"
    assert pkt.parent_trace_id is None


def test_emp_packet_reply():
    original = EMPPacket(
        source="worker",
        intent_type=INTENT_TASK_RESULT,
        action="result",
        payload={"stdout": "hello"},
        token_budget=500,
    )
    reply = original.reply(
        source="qa",
        intent_type="qa_verdict",
        action="APPROVE",
        payload={"verdict": "APPROVE"},
    )
    assert reply.parent_trace_id == original.trace_id
    assert reply.target == "worker"  # replies go to original source
    assert reply.token_budget == 500


def test_emp_packet_serialization():
    pkt = EMPPacket(
        source="test",
        intent_type="test_intent",
        action="test action",
    )
    data = pkt.model_dump()
    assert data["source"] == "test"
    # Round-trip
    restored = EMPPacket(**data)
    assert restored.trace_id == pkt.trace_id
