from __future__ import annotations

from fccs_agent.pipeline.planner import Planner
from fccs_agent.pipeline.types import Plan
from fccs_agent.pipeline.anthropic_adapter import AnthropicAdapter


class AnthropicPlanner(Planner):
    """Planner wrapper that delegates to an Anthropic adapter."""

    def __init__(self, adapter: AnthropicAdapter):
        self._adapter = adapter

    async def plan(self, query: str, tool_catalog: list[dict]) -> Plan:
        return await self._adapter.plan(query, tool_catalog)
