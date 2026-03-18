"""OpenTower V1.0 — Main Entry Point.

REPL loop:
    Load company.yaml → boot agents → accept natural-language commands →
    CEO decomposes → Worker executes → QA verifies → print trace.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

from opentower.actions.github import register_github_actions
from opentower.actions.registry import ActionRegistry
from opentower.actions.shell import register_shell_actions
from opentower.agents.ceo import CEOAgent
from opentower.agents.qa import QAAgent
from opentower.agents.worker import WorkerAgent
from opentower.bus.event_bus import EMPBus
from opentower.llm.client import LLMClient
from opentower.memory.state_wall import StateWall
from opentower.schema.company import load_company
from opentower.schema.emp import EMPPacket, INTENT_QA_VERDICT, INTENT_USER_REQUEST

# ── Logging ────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(name)-28s │ %(levelname)-5s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("opentower")

# ── ANSI colours (for terminal output) ─────────────────────────────
C_CYAN = "\033[96m"
C_GREEN = "\033[92m"
C_RED = "\033[91m"
C_YELLOW = "\033[93m"
C_DIM = "\033[2m"
C_BOLD = "\033[1m"
C_RESET = "\033[0m"


def _print_banner() -> None:
    print(
        f"""{C_CYAN}{C_BOLD}
    ╔══════════════════════════════════════════════════╗
    ║           🏢  O P E N   T O W E R  🏢           ║
    ║        5-Layer Multi-Agent Architecture          ║
    ║                  v1.0 · MVP                      ║
    ╚══════════════════════════════════════════════════╝{C_RESET}
    """
    )


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
        idx = packet.payload.get("task_index", "?")
        total = packet.payload.get("total_tasks", "?")

        color = C_GREEN if verdict == "APPROVE" else C_RED
        print(
            f"\n{C_DIM}──────────────────────────────────────────{C_RESET}"
        )
        print(
            f"  {C_BOLD}QA Verdict [{idx + 1 if isinstance(idx, int) else idx}/{total}]{C_RESET}"
        )
        print(f"  Status : {color}{verdict}{C_RESET}")
        print(f"  Reason : {reason}")

        result = packet.payload.get("inspected_result", {})
        if "stdout" in result and result["stdout"]:
            print(f"  {C_DIM}Output :{C_RESET}")
            for line in result["stdout"].split("\n")[:20]:
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
        """Wait until all expected verdicts are received."""
        try:
            await asyncio.wait_for(self._done_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            print(f"{C_YELLOW}  ⏱ Timed out waiting for all verdicts{C_RESET}")


async def run() -> None:
    """Bootstrap the full pipeline and enter the REPL."""
    _print_banner()

    # ── Locate company.yaml ────────────────────────────────────────
    yaml_path = Path(os.getenv("OPENTOWER_CONFIG", "company.yaml"))
    if not yaml_path.exists():
        # Try from package root
        yaml_path = Path(__file__).resolve().parent.parent / "company.yaml"
    if not yaml_path.exists():
        print(f"{C_RED}ERROR: company.yaml not found{C_RESET}")
        sys.exit(1)

    config = load_company(yaml_path)
    print(f"  {C_DIM}Empire : {config.empire.name} v{config.empire.version}{C_RESET}")
    print(f"  {C_DIM}Nodes  : {', '.join(config.nodes.keys())}{C_RESET}")

    # ── Infrastructure ─────────────────────────────────────────────
    bus = EMPBus()
    llm = LLMClient()
    state = StateWall("opentower.db")
    await state.open()

    registry = ActionRegistry()
    register_shell_actions(registry)
    register_github_actions(registry)
    print(f"  {C_DIM}Actions: {', '.join(registry.available_actions)}{C_RESET}")

    # ── Agents ─────────────────────────────────────────────────────
    ceo = CEOAgent("ceo", config.nodes["ceo"], bus, llm, state)
    worker = WorkerAgent("worker", config.nodes["worker"], bus, llm, state, registry=registry)
    qa = QAAgent("qa", config.nodes["qa"], bus, llm, state)

    ceo.register()
    worker.register()
    qa.register()

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

            # Publish user request
            packet = EMPPacket(
                source="user",
                intent_type=INTENT_USER_REQUEST,
                action=user_input,
                payload={"raw_input": user_input},
                token_budget=config.nodes["ceo"].token_budget,
            )

            verdict_printer.verdicts.clear()
            verdict_printer.set_pending(1)  # conservative; will be updated

            await bus.publish(packet)

            # Wait for the pipeline to finish
            await verdict_printer.wait_done(timeout=120.0)

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
    print(f"{C_DIM}Goodbye.{C_RESET}")


def main() -> None:
    """Sync entry point."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
