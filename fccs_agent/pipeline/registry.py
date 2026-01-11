from __future__ import annotations

from typing import Any, Callable, Awaitable


class ToolRegistry:
    def __init__(self, tool_definitions: list[dict], executor: Callable[..., Awaitable[dict[str, Any]]]):
        self._tool_definitions = tool_definitions
        self._executor = executor
        self._tool_index = {tool["name"]: tool for tool in tool_definitions}

    def list_definitions(self) -> list[dict]:
        return list(self._tool_definitions)

    def get_definition(self, name: str) -> dict | None:
        return self._tool_index.get(name)

    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        session_id: str,
        user_query: str,
    ) -> dict[str, Any]:
        return await self._executor(
            tool_name,
            arguments,
            session_id=session_id,
            user_query=user_query,
        )
