"""Skills package — pluggable tool ecosystem.

Skills are the agent's capabilities. Each skill is a Python module
with functions decorated with @skill. Skills are discovered at
runtime from config.yaml.

Usage::

    from opentower.skills import SkillRegistry, skill

    @skill("greet", description="Say hello")
    async def greet(name: str = "world"):
        return {"message": f"Hello, {name}!"}
"""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

from opentower.config import SkillConfig

logger = logging.getLogger("opentower.skills")


@dataclass
class SkillInfo:
    """Metadata + callable for a single skill."""
    name: str
    description: str
    parameters: str
    execute: Callable[..., Awaitable[dict]]


class SkillRegistry:
    """Discovers and manages skills from config.

    Usage::

        registry = SkillRegistry()
        registry.load_from_config(config.enabled_skills)
        result = await registry.call("shell", command="ls")
    """

    def __init__(self) -> None:
        self._skills: dict[str, SkillInfo] = {}

    def register(self, info: SkillInfo) -> None:
        """Register a skill manually."""
        self._skills[info.name] = info
        logger.info("Skill registered: %s — %s", info.name, info.description)

    def load_from_config(self, skill_configs: list[SkillConfig]) -> None:
        """Auto-discover and load skills from config entries."""
        for sc in skill_configs:
            if sc.type == "python":
                self._load_python_skill(sc)
            elif sc.type == "cli":
                logger.info("CLI skill '%s' — will call subprocess directly", sc.name)
            elif sc.type == "mcp":
                logger.info("MCP skill '%s' — bridge not yet implemented", sc.name)
            else:
                logger.warning("Unknown skill type: %s", sc.type)

    def _load_python_skill(self, sc: SkillConfig) -> None:
        """Import a Python module and register its @skill-decorated functions."""
        if not sc.module:
            logger.warning("Python skill '%s' has no module path", sc.name)
            return

        try:
            mod = importlib.import_module(sc.module)
        except ImportError as e:
            logger.error("Failed to import skill '%s' (%s): %s", sc.name, sc.module, e)
            return

        # Find all @skill-decorated functions in the module
        registered = 0
        for attr_name in dir(mod):
            obj = getattr(mod, attr_name)
            if hasattr(obj, "_skill_info"):
                info: SkillInfo = obj._skill_info
                info.execute = obj
                self.register(info)
                registered += 1

        if registered == 0:
            # If no @skill decorators, try module-level SKILLS dict
            skills_dict = getattr(mod, "SKILLS", None)
            if skills_dict and isinstance(skills_dict, dict):
                for name, fn in skills_dict.items():
                    self.register(SkillInfo(
                        name=name,
                        description=getattr(fn, "__doc__", name) or name,
                        parameters="",
                        execute=fn,
                    ))
                    registered += 1

        logger.info("Loaded %d skills from %s", registered, sc.module)

    async def call(self, name: str, **kwargs: Any) -> dict:
        """Execute a skill by name."""
        skill = self._skills.get(name)
        if skill is None:
            return {"error": f"Unknown skill: {name}. Available: {', '.join(self.available)}"}
        return await skill.execute(**kwargs)

    @property
    def available(self) -> list[str]:
        return sorted(self._skills)

    @property
    def all_skills(self) -> dict[str, SkillInfo]:
        return dict(self._skills)

    def __contains__(self, name: str) -> bool:
        return name in self._skills

    def __getitem__(self, name: str) -> SkillInfo:
        return self._skills[name]


def skill(name: str, *, description: str = "", parameters: str = ""):
    """Decorator to register a function as a skill.

    Usage::

        @skill("list_files", description="List directory contents")
        async def list_files(path: str = "."):
            ...
    """
    def decorator(fn):
        fn._skill_info = SkillInfo(
            name=name,
            description=description or fn.__doc__ or name,
            parameters=parameters,
            execute=fn,
        )
        return fn
    return decorator
