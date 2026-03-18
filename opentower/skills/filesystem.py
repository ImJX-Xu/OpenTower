"""Filesystem skill — read, write, list files."""

from __future__ import annotations

import os
from pathlib import Path

from opentower.skills import skill


@skill(
    "read_file",
    description="Read the contents of a file",
    parameters='{"path": "string (required) — file path"}',
)
async def read_file(path: str = "") -> dict:
    """Read a file and return its contents."""
    if not path:
        return {"error": "No path provided"}
    p = Path(path)
    if not p.exists():
        return {"error": f"File not found: {path}"}
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
        return {"content": content[:10000], "size": p.stat().st_size}
    except Exception as e:
        return {"error": str(e)}


@skill(
    "write_file",
    description="Write content to a file (creates or overwrites)",
    parameters='{"path": "string", "content": "string"}',
)
async def write_file(path: str = "", content: str = "") -> dict:
    """Write content to a file."""
    if not path:
        return {"error": "No path provided"}
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(content, encoding="utf-8")
        return {"status": "ok", "path": path, "bytes_written": len(content.encode())}
    except Exception as e:
        return {"error": str(e)}


@skill(
    "list_dir",
    description="List contents of a directory",
    parameters='{"path": "string (default: current dir)"}',
)
async def list_directory(path: str = ".") -> dict:
    """List directory contents."""
    p = Path(path)
    if not p.exists():
        return {"error": f"Directory not found: {path}"}
    if not p.is_dir():
        return {"error": f"Not a directory: {path}"}

    entries = []
    try:
        for entry in sorted(p.iterdir()):
            info = {"name": entry.name, "is_dir": entry.is_dir()}
            if not entry.is_dir():
                try:
                    info["size"] = entry.stat().st_size
                except OSError:
                    pass
            entries.append(info)
    except PermissionError:
        return {"error": f"Permission denied: {path}"}

    return {"path": str(p.resolve()), "entries": entries[:200]}
