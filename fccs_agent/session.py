"""Session management for FCCS agent.

This module provides session ID tracking without circular imports.
"""

from __future__ import annotations

import uuid
import contextvars
from typing import Any

# Process-level stable session ID (fallback when no client_id)
_process_session_id = f"mcp-{uuid.uuid4().hex[:8]}"

# Context variable for current request's session ID
_current_session: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_session", default=_process_session_id
)


def get_session_id(ctx: Any | None) -> str:
    """Get session ID from context or use stable fallback.

    Priority:
    1. ctx.client_id (MCP client identifier)
    2. ctx.request_context.meta.progressToken (alternative MCP identifier)
    3. Process-level stable session ID (fallback)
    """
    session_id = _process_session_id

    if ctx is not None:
        try:
            # Try client_id first
            client_id = getattr(ctx, "client_id", None)
            if client_id:
                session_id = f"mcp-{client_id}"
            else:
                # Try request_context for alternative identifiers
                request_ctx = getattr(ctx, "request_context", None)
                if request_ctx:
                    meta = getattr(request_ctx, "meta", None)
                    if meta:
                        progress_token = getattr(meta, "progressToken", None)
                        if progress_token:
                            session_id = f"mcp-{progress_token}"
        except Exception:
            pass

    # Store in context variable for other tools to access
    _current_session.set(session_id)
    return session_id


def get_current_session() -> str:
    """Get the current session ID from context variable.

    This allows tools to access the session without needing the MCP context directly.
    """
    return _current_session.get()


def set_current_session(session_id: str) -> None:
    """Set the current session ID explicitly."""
    _current_session.set(session_id)
