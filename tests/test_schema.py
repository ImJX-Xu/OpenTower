"""Tests for company.yaml V2.0 schema — hierarchy + node memory."""

import pytest
from pathlib import Path

from opentower.schema.company import CompanyConfig, load_company, NodeConfig, EmpireInfo, HierarchyNode


# ── Fixtures ────────────────────────────────────────────────────

@pytest.fixture
def config(tmp_path):
    """Load the real company.yaml for V2.0 testing."""
    yaml_file = Path(__file__).resolve().parent.parent / "company.yaml"
    return load_company(yaml_file)


@pytest.fixture
def minimal_config():
    """Minimal 3-level hierarchy for unit testing."""
    return CompanyConfig(
        empire=EmpireInfo(name="Test", version="2.0"),
        nodes={
            "boss": NodeConfig(role="Boss", prompt="boss prompt", level="executive"),
            "mgr": NodeConfig(role="Manager", prompt="mgr prompt", level="middle"),
            "worker": NodeConfig(role="Worker", prompt="worker prompt", level="worker"),
            "qa": NodeConfig(role="QA", prompt="qa prompt", level="qa"),
        },
        hierarchy={
            "boss": HierarchyNode(subordinates=["mgr"]),
            "mgr": HierarchyNode(subordinates=["worker"]),
        },
    )


# ── Schema Tests ────────────────────────────────────────────────

def test_load_v2_yaml(config):
    """Real company.yaml parses with hierarchy."""
    assert config.empire.version == "2.0"
    assert "chairman" in config.nodes
    assert "ceo" in config.nodes
    assert "vp_engineering" in config.nodes
    assert "worker" in config.nodes
    assert "qa" in config.nodes


def test_hierarchy_subordinates(config):
    """Chairman has CEO as subordinate."""
    subs = config.get_subordinates("chairman")
    assert subs == ["ceo"]


def test_hierarchy_superior(config):
    """CEO's superior is chairman."""
    assert config.get_superior("ceo") == "chairman"


def test_hierarchy_root(config):
    """Root node is chairman."""
    assert config.get_root() == "chairman"


def test_is_manager(config):
    """Nodes with subordinates are managers."""
    assert config.is_manager("chairman")
    assert config.is_manager("ceo")
    assert config.is_manager("vp_engineering")
    assert not config.is_manager("qa")


def test_is_worker(config):
    """Leaf nodes are workers."""
    assert config.is_worker("worker")
    assert config.is_worker("ops_worker")
    assert not config.is_worker("ceo")


def test_all_managers(config):
    """all_managers returns all nodes with subordinates."""
    managers = config.all_managers
    assert "chairman" in managers
    assert "ceo" in managers
    assert "worker" not in managers


def test_all_workers(config):
    """all_workers returns leaf non-QA nodes."""
    workers = config.all_workers
    assert "worker" in workers
    assert "ops_worker" in workers
    assert "qa" not in workers


def test_node_level(config):
    """Nodes have correct level assignments."""
    assert config.nodes["chairman"].level == "executive"
    assert config.nodes["ceo"].level == "c_suite"
    assert config.nodes["worker"].level == "worker"
    assert config.nodes["qa"].level == "qa"


def test_minimal_config(minimal_config):
    """Minimal config hierarchy works."""
    assert minimal_config.get_root() == "boss"
    assert minimal_config.get_subordinates("boss") == ["mgr"]
    assert minimal_config.get_subordinates("mgr") == ["worker"]
    assert minimal_config.is_manager("boss")
    assert minimal_config.is_worker("worker")
    assert minimal_config.get_superior("worker") == "mgr"
