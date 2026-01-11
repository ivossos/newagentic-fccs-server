from __future__ import annotations

from fccs_agent.pipeline.planner import Planner
from fccs_agent.pipeline.registry import ToolRegistry
from fccs_agent.pipeline.types import PipelineResult, Plan, ToolExecutionResult


class AgenticPipeline:
    def __init__(self, planner: Planner, registry: ToolRegistry):
        self._planner = planner
        self._registry = registry

    async def run(self, query: str, session_id: str) -> PipelineResult:
        tool_catalog = self._registry.list_definitions()
        plan = await self._planner.plan(query, tool_catalog)

        if not plan.steps:
            return PipelineResult(
                status="error",
                plan=plan,
                results=[],
                error="No executable plan generated",
            )

        results: list[ToolExecutionResult] = []
        status = "success"

        for step in plan.steps:
            result = await self._registry.execute(step.tool_name, step.arguments, session_id, query)
            results.append(ToolExecutionResult(step.tool_name, step.arguments, result))
            if isinstance(result, dict) and result.get("status") == "error":
                status = "partial"

        return PipelineResult(status=status, plan=plan, results=results)
