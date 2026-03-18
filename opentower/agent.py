"""Agent — the core class of the Agent OS.

One class. No hierarchy. No rigid roles.
Behavior is defined by config.yaml, not by subclasses.

Modes:
    - Simple: think → act → reflect → respond (single-step)
    - Planner: plan → execute steps → review → respond (multi-step)
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
    """The core agent — supports both simple tool-calling and multi-step planning.

    Simple mode (default): think → act → reflect loop.
    Planner mode (complex tasks): plan steps → execute each → review → respond.

    Usage::

        agent = Agent(config, llm, memory, skills)
        response = await agent.run("list the files in /tmp")
        response = await agent.run("研究竞品并写报告", mode="plan")
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
        self._max_iterations = 10

    async def run(self, user_input: str, *, context: str = "", mode: str = "auto") -> str:
        """Execute a user request.

        Args:
            user_input: Natural language request.
            context: Optional extra context.
            mode: "auto" (LLM decides), "simple" (force single-step), "plan" (force multi-step).
        """
        logger.info("Agent received: %s", user_input[:80])

        if self.memory:
            await self.memory.record("user", user_input[:500])

        # Inject lessons learned for relevant skills
        lessons_ctx = ""
        if self.memory:
            lessons_ctx = await self.memory.get_lessons()

        full_context = context
        if lessons_ctx:
            full_context += f"\n\nLessons from past failures:\n{lessons_ctx}"

        # Choose mode
        if mode == "plan" or (mode == "auto" and self._looks_complex(user_input)):
            response = await self._run_planner(user_input, full_context)
        else:
            response = await self._run_simple(user_input, full_context)

        if self.memory:
            await self.memory.record("agent", response[:500])

        logger.info("Agent response: %s", response[:80])
        return response

    # ── Simple Mode (think→act→reflect) ───────────────────────

    async def _run_simple(self, user_input: str, context: str) -> str:
        """Single think→act→reflect loop."""
        tools_desc = self._format_tools()
        messages = self._build_messages(user_input, tools_desc, context)

        results = []
        for iteration in range(self._max_iterations):
            raw = await self._call_llm(messages)
            decision = self._parse_decision(raw)

            if decision["type"] == "respond":
                return decision["content"]

            if decision["type"] == "call_skill":
                skill_name = decision["skill"]
                skill_args = decision["args"]
                logger.info("Skill call: %s(%s)", skill_name, str(skill_args)[:60])

                result = await self._execute_skill(skill_name, skill_args)
                results.append({"skill": skill_name, "result": result})

                # Record lesson if skill failed
                if "error" in result and self.memory:
                    await self.memory.record_lesson(
                        skill_name,
                        str(skill_args)[:200],
                        str(result["error"])[:300],
                    )

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

            return raw

        return f"达到最大迭代次数 ({self._max_iterations})。中间结果：\n" + \
               "\n".join(f"- {r['skill']}: {str(r['result'])[:100]}" for r in results)

    # ── Planner Mode (plan→execute→review) ────────────────────

    async def _run_planner(self, user_input: str, context: str) -> str:
        """Multi-step planner: decompose → execute each step → review → respond."""
        tools_desc = self._format_tools()

        # Step 1: PLAN — ask LLM to decompose into steps
        plan_prompt = (
            f"{self.config.agent.system_prompt}\n\n{tools_desc}\n\n"
            "You are in PLANNER mode. Decompose the user's request into ordered steps.\n"
            "Respond with EXACTLY this JSON format:\n"
            '{"action": "plan", "steps": [\n'
            '  {"description": "step description", "skill": "skill_name", "args": {args}},\n'
            '  ...\n'
            ']}\n\n'
            "Each step should use one skill. Order steps logically (dependencies first).\n"
            "Use 2-8 steps. If the task is simple, use fewer steps."
        )

        plan_messages = [
            {"role": "system", "content": plan_prompt},
        ]
        if context:
            plan_messages.append({"role": "system", "content": f"Context:\n{context}"})
        plan_messages.append({"role": "user", "content": user_input})

        raw_plan = await self._call_llm(plan_messages)
        plan = self._parse_plan(raw_plan)

        if not plan:
            logger.info("Planner couldn't decompose — falling back to simple mode")
            return await self._run_simple(user_input, context)

        logger.info("Plan: %d steps — %s", len(plan), ", ".join(s.get("skill", "?") for s in plan))

        # Step 2: EXECUTE — run each step
        step_results = []
        for i, step in enumerate(plan):
            desc = step.get("description", f"Step {i+1}")
            skill_name = step.get("skill", "")
            skill_args = step.get("args", {})

            logger.info("Step %d/%d: %s (%s)", i+1, len(plan), desc[:40], skill_name)

            if skill_name and skill_name in self.skills:
                result = await self._execute_skill(skill_name, skill_args)
                if "error" in result and self.memory:
                    await self.memory.record_lesson(skill_name, str(skill_args)[:200], str(result["error"])[:300])
            else:
                result = {"skipped": f"Skill '{skill_name}' not available"}

            step_results.append({
                "step": i + 1,
                "description": desc,
                "skill": skill_name,
                "result": result,
            })

        # Step 3: REVIEW — summarize results
        review_messages = [
            {"role": "system", "content": (
                f"{self.config.agent.system_prompt}\n\n"
                "You are reviewing the results of a multi-step task execution.\n"
                "Summarize the overall outcome for the user.\n"
                "Mention any failures or issues.\n"
                "Respond naturally in the user's language."
            )},
            {"role": "user", "content": (
                f"Original request: {user_input}\n\n"
                f"Execution results:\n"
                f"```json\n{json.dumps(step_results, ensure_ascii=False, default=str)[:3000]}\n```\n\n"
                "Summarize the results for the user."
            )},
        ]

        response = await self._call_llm(review_messages)
        # Parse in case LLM wraps in JSON
        decision = self._parse_decision(response)
        if decision["type"] == "respond":
            return decision["content"]
        return response

    def _parse_plan(self, raw: str) -> list[dict]:
        """Parse LLM plan output into a list of steps."""
        cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        cleaned = re.sub(r"```(?:json)?\s*", "", cleaned).strip()
        cleaned = re.sub(r"```\s*$", "", cleaned).strip()

        # Try to extract plan JSON
        for match in re.finditer(r"\{.*\}", cleaned, re.DOTALL):
            try:
                obj = json.loads(match.group())
                if "steps" in obj and isinstance(obj["steps"], list):
                    return obj["steps"][:8]  # cap at 8 steps
            except json.JSONDecodeError:
                continue

        return []

    @staticmethod
    def _looks_complex(user_input: str) -> bool:
        """Heuristic: does this request need multi-step planning?"""
        complex_signals = [
            "然后", "之后", "接着", "最后", "首先",  # Chinese sequence words
            "then", "after", "finally", "first", "next",  # English
            "步骤", "计划", "流程", "报告",  # Chinese: steps/plan/process/report
            " and then ", " step ",
        ]
        long_enough = len(user_input) > 80
        has_signals = any(s in user_input.lower() for s in complex_signals)
        return long_enough and has_signals

    # ── Shared Internals ──────────────────────────────────────

    def _format_tools(self) -> str:
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
        if context:
            messages.append({"role": "system", "content": f"Context:\n{context}"})
        messages.append({"role": "user", "content": user_input})
        return messages

    async def _call_llm(self, messages: list[dict]) -> str:
        text, usage = await self.llm.chat(
            messages,
            max_tokens=self.config.agent.llm.max_tokens,
            temperature=self.config.agent.llm.temperature,
        )
        logger.debug("LLM used %d tokens", usage.total)
        return text

    def _parse_decision(self, raw: str) -> dict:
        cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        if cleaned.startswith("<think>"):
            idx = cleaned.find("{")
            cleaned = cleaned[idx:] if idx != -1 else cleaned

        cleaned = re.sub(r"```(?:json)?\s*", "", cleaned).strip()
        cleaned = re.sub(r"```\s*$", "", cleaned).strip()

        for match in re.finditer(r"\{[^{}]*\}", cleaned):
            try:
                obj = json.loads(match.group())
                if "action" in obj:
                    if obj["action"] == "call_skill":
                        return {"type": "call_skill", "skill": obj.get("skill", ""), "args": obj.get("args", {})}
                    if obj["action"] == "respond":
                        return {"type": "respond", "content": obj.get("content", "")}
            except json.JSONDecodeError:
                continue

        for match in re.finditer(r"\{.*\}", cleaned, re.DOTALL):
            try:
                obj = json.loads(match.group())
                if "action" in obj:
                    if obj["action"] == "call_skill":
                        return {"type": "call_skill", "skill": obj.get("skill", ""), "args": obj.get("args", {})}
                    if obj["action"] == "respond":
                        return {"type": "respond", "content": obj.get("content", "")}
            except json.JSONDecodeError:
                continue

        return {"type": "respond", "content": cleaned or raw}

    async def _execute_skill(self, name: str, args: dict) -> dict:
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
