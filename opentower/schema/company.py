"""Layer 1: Organization Definition — YAML → Pydantic models."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class EmpireInfo(BaseModel):
    """Top-level empire metadata."""

    name: str
    version: str


class NodeConfig(BaseModel):
    """Configuration for a single agent node."""

    role: str
    prompt: str
    permissions: list[str] = Field(default_factory=list)
    token_budget: int = 4096


class CompanyConfig(BaseModel):
    """Root configuration parsed from company.yaml."""

    empire: EmpireInfo
    nodes: dict[str, NodeConfig]


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
