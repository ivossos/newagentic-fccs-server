from __future__ import annotations

import asyncio
from typing import Any

# Import session functions from dedicated module (no circular imports)
from fccs_agent.session import get_session_id, get_current_session, set_current_session

_initialized = False
_init_lock = asyncio.Lock()
_session_stats: dict[str, dict[str, Any]] = {}


async def ensure_initialized() -> None:
    global _initialized
    if _initialized:
        return
    async with _init_lock:
        if _initialized:
            return
        # Lazy import to avoid circular dependency
        from fccs_agent.agent import initialize_agent
        await initialize_agent()
        _initialized = True


def record_tool_result(session_id: str, result: dict[str, Any]) -> None:
    stats = _session_stats.setdefault(session_id, {"tool_count": 0, "has_errors": False})
    stats["tool_count"] += 1
    if isinstance(result, dict) and result.get("status") == "error":
        stats["has_errors"] = True


def finalize_sessions() -> None:
    # Lazy import to avoid circular dependency
    from fccs_agent.agent import finalize_session
    for session_id, stats in list(_session_stats.items()):
        tool_count = stats.get("tool_count", 0)
        if tool_count <= 0:
            continue
        outcome = "partial" if stats.get("has_errors") else "success"
        try:
            finalize_session(session_id, outcome)
        except Exception:
            pass


async def shutdown() -> None:
    if _initialized:
        finalize_sessions()
        # Lazy import to avoid circular dependency
        from fccs_agent.agent import close_agent
        await close_agent()
