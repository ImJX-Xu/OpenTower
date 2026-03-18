"""Layer 1: Organization Definition — YAML → Pydantic models (V2.0).

Adds hierarchy tree and level classification to support multi-tier
org structures.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field


class EmpireInfo(BaseModel):
    """Top-level empire metadata."""

    name: str
    version: str


class HierarchyNode(BaseModel):
    """A node in the org tree — defines who reports to whom."""

    subordinates: list[str] = Field(default_factory=list)


class NodeConfig(BaseModel):
    """Configuration for a single agent node."""

    role: str
    prompt: str
    permissions: list[str] = Field(default_factory=list)
    token_budget: int = 4096
    level: str = "worker"  # executive | c_suite | senior | middle | worker | qa


class CompanyConfig(BaseModel):
    """Root configuration parsed from company.yaml."""

    empire: EmpireInfo
    nodes: dict[str, NodeConfig]
    hierarchy: dict[str, HierarchyNode] = Field(default_factory=dict)

    def get_subordinates(self, node_id: str) -> list[str]:
        """Return the list of subordinate node IDs for a given node."""
        entry = self.hierarchy.get(node_id)
        return entry.subordinates if entry else []

    def get_superior(self, node_id: str) -> Optional[str]:
        """Return the superior (parent) of a node, or None if it's the root."""
        for sup_id, entry in self.hierarchy.items():
            if node_id in entry.subordinates:
                return sup_id
        return None

    def get_root(self) -> Optional[str]:
        """Return the root node ID (the one with no superior)."""
        all_subordinates = set()
        for entry in self.hierarchy.values():
            all_subordinates.update(entry.subordinates)
        for node_id in self.hierarchy:
            if node_id not in all_subordinates:
                return node_id
        return None

    def is_manager(self, node_id: str) -> bool:
        """True if this node has subordinates (i.e. it delegates)."""
        return bool(self.get_subordinates(node_id))

    def is_worker(self, node_id: str) -> bool:
        """True if this node has no subordinates (leaf executor)."""
        return not self.is_manager(node_id) and node_id in self.nodes

    @property
    def all_managers(self) -> list[str]:
        """All node IDs that have subordinates."""
        return [nid for nid in self.hierarchy if self.get_subordinates(nid)]

    @property
    def all_workers(self) -> list[str]:
        """All leaf node IDs (no subordinates, not QA)."""
        return [
            nid for nid in self.nodes
            if self.is_worker(nid) and self.nodes[nid].level != "qa"
        ]


def load_company(path: str | Path = "company.yaml") -> CompanyConfig:
    """Load and validate company.yaml into a strongly-typed config.

    Args:
        path: Path to the YAML file.

    Returns:
        A validated CompanyConfig instance.

    Raises:
        FileNotFoundError: If the YAML file does not exist.
        pydantic.ValidationError: If the YAML structure is invalid.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Company config not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    return CompanyConfig(**raw)
