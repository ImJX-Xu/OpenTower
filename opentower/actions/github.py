"""Action: GitHub API — stub implementations for MVP.

These are placeholder actions that simulate GitHub operations.
Replace with real ``httpx`` calls to the GitHub REST/GraphQL API later.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("opentower.actions.github")


async def github_create_issue(payload: dict[str, Any]) -> dict[str, Any]:
    """Stub: Simulate creating a GitHub issue."""
    title = payload.get("title", "Untitled")
    body = payload.get("body", "")
    repo = payload.get("repo", "owner/repo")
    logger.info("[STUB] Creating issue '%s' in %s", title, repo)
    return {
        "status": "simulated",
        "issue_url": f"https://github.com/{repo}/issues/999",
        "title": title,
        "body": body,
    }


async def github_list_repos(payload: dict[str, Any]) -> dict[str, Any]:
    """Stub: Simulate listing GitHub repositories."""
    logger.info("[STUB] Listing repos")
    return {
        "status": "simulated",
        "repos": [
            "OpenTower/core",
            "OpenTower/actions",
            "OpenTower/docs",
        ],
    }


def register_github_actions(registry) -> None:  # noqa: ANN001
    """Register all GitHub actions into the given ActionRegistry."""
    registry._handlers["github_create_issue"] = github_create_issue
    registry._handlers["github_list_repos"] = github_list_repos
