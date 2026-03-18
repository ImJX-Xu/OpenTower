"""Agents package (V2.0).

Exports:
    BaseAgent     — abstract base with memory integration
    ManagerAgent  — generic task decomposer for any org level
    WorkerAgent   — leaf executor
    QAAgent       — dual verification inspector
"""

from .base import BaseAgent
from .manager import ManagerAgent
from .worker import WorkerAgent
from .qa import QAAgent

__all__ = ["BaseAgent", "ManagerAgent", "WorkerAgent", "QAAgent"]
