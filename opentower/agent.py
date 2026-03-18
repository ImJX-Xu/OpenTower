"""Agent — the single core class of the Agent OS.

One class. No hierarchy. No rigid roles.
Behavior is defined by config.yaml, not by subclasses.

Loop: think → act → reflect → (loop or done)
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from opentower.config import Config
from opentower.llm.client import LLMClient
from opentower.memory.node_memory import NodeMemory

logger = logging.getLogger("opentower.agent")


class Agent:
    """The core agent — a single think→act→reflect loop.

    Skills are injected at init. The agent uses the LLM to decide
    which skill to call, calls it, checks the result, and either
    loops or returns.

    Usage::

        agent = Agent(config, llm, memory, skills)
        response = await agent.run("list the files in /tmp")
    """

    def __init__(
        self,
        config: Config,
        llm: LLMClient,
        memory: NodeMemory | None = None,
        skills: dict[str, Any] | None = None,
    ) -> None:
        self.config = config
        self.llm = llm
        self.memory = memory
        self.skills = skills or {}
        self._max_iterations = 10  # safety: max think→act loops

    async def run(self, user_input: str, *, context: str = "") -> str:
        """Execute a user request through the think→act→reflect loop.

        Args:
            user_input: The user's natural language request.
            context: Optional extra context (channel, conversation history, etc.)

        Returns:
            Final response text to send back to the user.
        """
        logger.info("Agent received: %s", user_input[:80])

        # Record input
        if self.memory:
            await self.memory.record("user", user_input[:500])

        # Build tool descriptions for the LLM
        tools_desc = self._format_tools()
        messages = self._build_messages(user_input, tools_desc, context)

        # Think → Act → Reflect loop
        results = []
        for iteration in range(self._max_iterations):
            # THINK: ask LLM what to do
            raw = await self._call_llm(messages)
            decision = self._parse_decision(raw)

            if decision["type"] == "respond":
                # Agent decided to respond directly (no tool needed)
                response = decision["content"]
                break

            if decision["type"] == "call_skill":
                # ACT: execute the skill
                skill_name = decision["skill"]
                skill_args = decision["args"]
                logger.info("Agent calling skill: %s(%s)", skill_name, str(skill_args)[:60])

                result = await self._execute_skill(skill_name, skill_args)
                results.append({"skill": skill_name, "result": result})

                # REFLECT: feed result back to LLM
                messages.append({"role": "assistant", "content": raw})
                messages.append({
                    "role": "user",
                    "content": (
                        f"Skill `{skill_name}` returned:\n"
                        f"```\n{json.dumps(result, ensure_ascii=False, default=str)[:1500]}\n```\n\n"
                        "Based on this result, decide next action or respond to the user."
                    ),
                })
                continue

            # Unknown decision type — treat as response
            response = raw
            break
        else:
            response = f"达到最大迭代次数 ({self._max_iterations})。中间结果：\n" + \
                       "\n".join(f"- {r['skill']}: {str(r['result'])[:100]}" for r in results)

        # Record output
        if self.memory:
            await self.memory.record("agent", response[:500])

        logger.info("Agent response: %s", response[:80])
        return response

    def _format_tools(self) -> str:
        """Format available skills as a tool description string for the LLM."""
        if not self.skills:
            return "No tools available."

        lines = ["Available tools (skills):"]
        for name, skill in self.skills.items():
            desc = getattr(skill, "description", name)
            params = getattr(skill, "parameters", "")
            lines.append(f"  - `{name}`: {desc}")
            if params:
                lines.append(f"    Parameters: {params}")
        return "\n".join(lines)

    def _build_messages(self, user_input: str, tools_desc: str, context: str) -> list[dict]:
        """Build the initial message chain for the LLM."""
        system = (
            f"{self.config.agent.system_prompt}\n\n"
            f"{tools_desc}\n\n"
            "To use a tool, respond with EXACTLY this JSON format (no other text):\n"
            '{"action": "call_skill", "skill": "<skill_name>", "args": {<arguments>}}\n\n'
            "To respond to the user directly (no tool needed):\n"
            '{"action": "respond", "content": "<your response>"}\n\n'
            "Always respond in the same language as the user."
        )

        messages = [{"role": "system", "content": system}]

        # Inject memory context
        if context:
            messages.append({"role": "system", "content": f"Context:\n{context}"})

        messages.append({"role": "user", "content": user_input})
        return messages

    async def _call_llm(self, messages: list[dict]) -> str:
        """Call the LLM and return raw text."""
        text, usage = await self.llm.chat(
            messages,
            max_tokens=self.config.agent.llm.max_tokens,
            temperature=self.config.agent.llm.temperature,
        )
        logger.debug("LLM used %d tokens", usage.total)
        return text

    def _parse_decision(self, raw: str) -> dict:
        """Parse LLM output into a structured decision.

        Handles: think tags, markdown fences, plain JSON, or plain text.
        """
        # Strip <think> tags
        cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        if cleaned.startswith("<think>"):
            idx = cleaned.find("{")
            cleaned = cleaned[idx:] if idx != -1 else cleaned

        # Strip markdown fences
        cleaned = re.sub(r"```(?:json)?\s*", "", cleaned).strip()
        cleaned = re.sub(r"```\s*$", "", cleaned).strip()

        # Try to parse as JSON
        for match in re.finditer(r"\{[^{}]*\}", cleaned):
            try:
                obj = json.loads(match.group())
                if "action" in obj:
                    if obj["action"] == "call_skill":
                        return {
                            "type": "call_skill",
                            "skill": obj.get("skill", ""),
                            "args": obj.get("args", {}),
                        }
                    if obj["action"] == "respond":
                        return {
                            "type": "respond",
                            "content": obj.get("content", ""),
                        }
            except json.JSONDecodeError:
                continue

        # Try nested JSON
        for match in re.finditer(r"\{.*\}", cleaned, re.DOTALL):
            try:
                obj = json.loads(match.group())
                if "action" in obj:
                    if obj["action"] == "call_skill":
                        return {
                            "type": "call_skill",
                            "skill": obj.get("skill", ""),
                            "args": obj.get("args", {}),
                        }
                    if obj["action"] == "respond":
                        return {
                            "type": "respond",
                            "content": obj.get("content", ""),
                        }
            except json.JSONDecodeError:
                continue

        # No JSON found — treat entire output as a direct response
        return {"type": "respond", "content": cleaned or raw}

    async def _execute_skill(self, name: str, args: dict) -> dict:
        """Execute a skill by name with given arguments."""
        skill = self.skills.get(name)
        if skill is None:
            return {"error": f"Unknown skill: {name}. Available: {', '.join(self.skills)}"}

        try:
            fn = getattr(skill, "execute", skill)
            if callable(fn):
                return await fn(**args) if args else await fn()
        except TypeError as e:
            return {"error": f"Skill '{name}' argument error: {e}"}
        except Exception as e:
            logger.exception("Skill '%s' failed", name)
            return {"error": f"Skill '{name}' failed: {e}"}
