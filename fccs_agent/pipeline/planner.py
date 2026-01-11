from __future__ import annotations

from typing import Protocol

from fccs_agent.pipeline.types import Plan


class Planner(Protocol):
    async def plan(self, query: str, tool_catalog: list[dict]) -> Plan:
        ...
