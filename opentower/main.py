"""OpenTower V2.0 — Main Entry Point.

Auto-builds the agent graph from company.yaml hierarchy:
    Chairman → CEO → VP → TechLead → Worker → QA

Each manager node is a ManagerAgent, each leaf is a WorkerAgent.
All nodes get independent per-node memory contexts.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

import aiosqlite

from opentower.actions.github import register_github_actions
from opentower.actions.registry import ActionRegistry
from opentower.actions.shell import register_shell_actions
from opentower.agents.manager import ManagerAgent
from opentower.agents.qa import QAAgent
from opentower.agents.worker import WorkerAgent
from opentower.bus.event_bus import EMPBus
from opentower.llm.client import LLMClient
from opentower.memory.node_memory import NodeMemory
from opentower.memory.state_wall import StateWall
from opentower.schema.company import CompanyConfig, load_company
from opentower.schema.emp import (
    EMPPacket,
    INTENT_QA_VERDICT,
    INTENT_TASK_ASSIGN,
    INTENT_USER_REQUEST,
)

# ── Logging ────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(name)-28s │ %(levelname)-5s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("opentower")

# ── ANSI colours ───────────────────────────────────────────────────
C_CYAN = "\033[96m"
C_GREEN = "\033[92m"
C_RED = "\033[91m"
C_YELLOW = "\033[93m"
C_MAGENTA = "\033[95m"
C_DIM = "\033[2m"
C_BOLD = "\033[1m"
C_RESET = "\033[0m"

# Level → color mapping for hierarchy visualization
LEVEL_COLORS = {
    "executive": C_MAGENTA,
    "c_suite": C_CYAN,
    "senior": C_GREEN,
    "middle": C_YELLOW,
    "worker": C_DIM,
    "qa": C_RED,
}


def _print_banner() -> None:
    print(
        f"""{C_CYAN}{C_BOLD}
    ╔══════════════════════════════════════════════════╗
    ║           🏢  O P E N   T O W E R  🏢           ║
    ║     Multi-Tier Agent Hierarchy Architecture      ║
    ║                  v2.0 · Beta                     ║
    ╚══════════════════════════════════════════════════╝{C_RESET}
    """
    )


def _print_hierarchy(config: CompanyConfig, node_id: str, depth: int = 0) -> None:
    """Recursively print the org tree."""
    node = config.nodes.get(node_id)
    if not node:
        return

    indent = "    " + "  │ " * depth
    color = LEVEL_COLORS.get(node.level, C_DIM)
    marker = "◆" if config.is_manager(node_id) else "●"
    print(f"{indent}{color}{marker} {node_id}{C_RESET} {C_DIM}({node.role.split('—')[0].strip()}){C_RESET}")

    for sub_id in config.get_subordinates(node_id):
        _print_hierarchy(config, sub_id, depth + 1)


class VerdictPrinter:
    """Subscriber that prints QA verdicts to the terminal."""

    def __init__(self) -> None:
        self.verdicts: list[EMPPacket] = []
        self.pending = 0
        self._done_event: asyncio.Event = asyncio.Event()

    def set_pending(self, n: int) -> None:
        self.pending = n
        self._done_event.clear()

    async def handle(self, packet: EMPPacket) -> None:
        self.verdicts.append(packet)

        verdict = packet.payload.get("verdict", "?")
        reason = packet.payload.get("reason", "")
        chain = packet.payload.get("chain", [])
        idx = packet.payload.get("task_index", "?")
        total = packet.payload.get("total_tasks", "?")

        color = C_GREEN if verdict == "APPROVE" else C_RED
        print(
            f"\n{C_DIM}──────────────────────────────────────────{C_RESET}"
        )
        print(
            f"  {C_BOLD}QA Verdict [{idx + 1 if isinstance(idx, int) else idx}/{total}]{C_RESET}"
        )
        if chain:
            print(f"  Chain  : {C_DIM}{' → '.join(chain)}{C_RESET}")
        print(f"  Status : {color}{verdict}{C_RESET}")
        print(f"  Reason : {reason[:200]}")

        result = packet.payload.get("inspected_result", {})
        if "stdout" in result and result["stdout"]:
            print(f"  {C_DIM}Output :{C_RESET}")
            for line in result["stdout"].split("\n")[:15]:
                print(f"    {C_DIM}{line}{C_RESET}")
        if "error" in result and result["error"]:
            print(f"  {C_RED}Error  : {result['error']}{C_RESET}")

        suggestion = packet.payload.get("suggestion")
        if suggestion:
            print(f"  {C_YELLOW}Hint   : {suggestion}{C_RESET}")

        # Track completion
        self.pending -= 1
        if self.pending <= 0:
            self._done_event.set()

    async def wait_done(self, timeout: float = 120.0) -> None:
        try:
            await asyncio.wait_for(self._done_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            print(f"{C_YELLOW}  ⏱ Timed out waiting for all verdicts{C_RESET}")


async def _build_agents(
    config: CompanyConfig,
    bus: EMPBus,
    llm: LLMClient,
    state: StateWall,
    memory_db: aiosqlite.Connection,
    registry: ActionRegistry,
) -> list:
    """Auto-build all agents from the hierarchy definition.

    - Nodes with subordinates → ManagerAgent
    - Leaf nodes (level=worker) → WorkerAgent
    - Nodes with level=qa → QAAgent
    """
    agents = []

    for node_id, node_config in config.nodes.items():
        # Create per-node memory
        mem = NodeMemory(node_id, memory_db)
        await mem.init()

        if node_config.level == "qa":
            agent = QAAgent(node_id, node_config, bus, llm, state, memory=mem)
            agent.register()
            agents.append(agent)
            continue

        if config.is_manager(node_id):
            subs = config.get_subordinates(node_id)
            agent = ManagerAgent(
                node_id, node_config, bus, llm, state,
                memory=mem, subordinates=subs,
            )
            # Root node listens for user_request, others for task_assign
            root = config.get_root()
            if node_id == root:
                agent.register(listen_intents=[INTENT_USER_REQUEST, INTENT_TASK_ASSIGN])
            else:
                agent.register(listen_intents=[INTENT_TASK_ASSIGN])
            agents.append(agent)
        else:
            # Leaf worker
            agent = WorkerAgent(
                node_id, node_config, bus, llm, state,
                memory=mem, registry=registry,
            )
            agent.register()
            agents.append(agent)

    return agents


async def run() -> None:
    """Bootstrap the full pipeline and enter the REPL."""
    _print_banner()

    # ── Locate company.yaml ────────────────────────────────────────
    yaml_path = Path(os.getenv("OPENTOWER_CONFIG", "company.yaml"))
    if not yaml_path.exists():
        yaml_path = Path(__file__).resolve().parent.parent / "company.yaml"
    if not yaml_path.exists():
        print(f"{C_RED}ERROR: company.yaml not found{C_RESET}")
        sys.exit(1)

    config = load_company(yaml_path)
    print(f"  {C_DIM}Empire : {config.empire.name} v{config.empire.version}{C_RESET}")

    # Print hierarchy tree
    root = config.get_root()
    if root:
        print(f"\n  {C_BOLD}Org Hierarchy:{C_RESET}")
        _print_hierarchy(config, root)
        # Also show QA nodes (not in hierarchy tree)
        for nid, nc in config.nodes.items():
            if nc.level == "qa":
                print(f"    {LEVEL_COLORS['qa']}▣ {nid}{C_RESET} {C_DIM}({nc.role.split('—')[0].strip()}){C_RESET}")

    # ── Infrastructure ─────────────────────────────────────────────
    bus = EMPBus()
    llm = LLMClient()
    state = StateWall("opentower.db")
    await state.open()

    # Per-node memory database
    memory_db = await aiosqlite.connect("opentower_memory.db")

    registry = ActionRegistry()
    register_shell_actions(registry)
    register_github_actions(registry)
    print(f"\n  {C_DIM}Actions  : {', '.join(registry.available_actions)}{C_RESET}")

    # ── Build Agent Graph ──────────────────────────────────────────
    agents = await _build_agents(config, bus, llm, state, memory_db, registry)
    print(f"  {C_DIM}Agents   : {len(agents)} nodes instantiated{C_RESET}")
    print(f"  {C_DIM}Managers : {', '.join(config.all_managers)}{C_RESET}")
    print(f"  {C_DIM}Workers  : {', '.join(config.all_workers)}{C_RESET}")

    verdict_printer = VerdictPrinter()
    bus.subscribe(INTENT_QA_VERDICT, verdict_printer.handle)

    await bus.start()
    print(f"\n  {C_GREEN}✓ All systems online. Type your intent below.{C_RESET}")
    print(f"  {C_DIM}Type 'exit' or 'quit' to shutdown.{C_RESET}\n")

    # ── REPL ───────────────────────────────────────────────────────
    try:
        while True:
            try:
                user_input = await asyncio.to_thread(
                    input, f"{C_CYAN}🏢 OpenTower>{C_RESET} "
                )
            except EOFError:
                break

            user_input = user_input.strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit"):
                break

            # Publish to the root node
            root_node = config.get_root() or "chairman"
            packet = EMPPacket(
                source="user",
                target=root_node,
                intent_type=INTENT_USER_REQUEST,
                action=user_input,
                payload={
                    "raw_input": user_input,
                    "intent": user_input,
                    "original_intent": user_input,
                },
                token_budget=config.nodes[root_node].token_budget,
            )

            verdict_printer.verdicts.clear()
            verdict_printer.set_pending(1)

            await bus.publish(packet)

            # Wait for pipeline
            await verdict_printer.wait_done(timeout=180.0)

            # Summary
            total = len(verdict_printer.verdicts)
            approved = sum(
                1 for v in verdict_printer.verdicts if v.payload.get("verdict") == "APPROVE"
            )
            print(
                f"\n  {C_DIM}Pipeline complete: "
                f"{approved}/{total} tasks approved{C_RESET}\n"
            )

    except KeyboardInterrupt:
        print(f"\n{C_YELLOW}Interrupted.{C_RESET}")

    # ── Cleanup ────────────────────────────────────────────────────
    await bus.stop()
    await state.close()
    await memory_db.close()
    print(f"{C_DIM}Goodbye.{C_RESET}")


def main() -> None:
    """Sync entry point."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
