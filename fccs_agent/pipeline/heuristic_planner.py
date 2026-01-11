from __future__ import annotations

import json

from fccs_agent.pipeline.planner import Planner
from fccs_agent.pipeline.types import Plan, PlanStep


class HeuristicPlanner(Planner):
    """Fallback planner that supports explicit tool invocation."""

    async def plan(self, query: str, tool_catalog: list[dict]) -> Plan:
        tool_names = {tool["name"] for tool in tool_catalog}
        query_text = (query or "").strip()

        step = self._plan_from_json(query_text, tool_names)
        if step:
            return Plan(query=query_text, steps=[step], notes="json" )

        step = self._plan_from_prefix(query_text, tool_names)
        if step:
            return Plan(query=query_text, steps=[step], notes="prefix" )

        return Plan(query=query_text, steps=[], notes="no_match")

    def _plan_from_json(self, query_text: str, tool_names: set[str]) -> PlanStep | None:
        if not (query_text.startswith("{") and query_text.endswith("}")):
            return None
        try:
            payload = json.loads(query_text)
        except json.JSONDecodeError:
            return None

        tool_name = payload.get("tool") or payload.get("name")
        if not tool_name or tool_name not in tool_names:
            return None

        arguments = payload.get("arguments") or payload.get("args") or {}
        if not isinstance(arguments, dict):
            return None

        return PlanStep(tool_name=tool_name, arguments=arguments, rationale="explicit json")

    def _plan_from_prefix(self, query_text: str, tool_names: set[str]) -> PlanStep | None:
        if not query_text:
            return None

        first_token = query_text.split()[0]
        if first_token in tool_names:
            return PlanStep(tool_name=first_token, arguments={}, rationale="tool name prefix")

        return None
