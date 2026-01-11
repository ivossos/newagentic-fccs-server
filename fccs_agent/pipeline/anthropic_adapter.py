from __future__ import annotations

import sys
from typing import Any

from fccs_agent.pipeline.types import Plan, PlanStep


# Planning system prompt for Claude
PLANNING_SYSTEM_PROMPT = """You are an intelligent FCCS (Financial Consolidation and Close) assistant.

Your task is to analyze the user's query and select the appropriate tools to fulfill their request.

Guidelines:
1. Analyze the user's intent carefully
2. Select only the tools that are necessary to complete the task
3. If multiple tools are needed, call them in the order they should be executed
4. Provide clear reasoning for each tool selection
5. Use the exact parameter names and types expected by each tool

If the query is unclear or cannot be handled by the available tools, do not call any functions.
Instead, explain what additional information is needed."""


def _tool_catalog_to_anthropic_tools(tool_catalog: list[dict]) -> list[dict]:
    """Convert MCP tool catalog to Anthropic tools format.

    Anthropic's tool format is very similar to MCP's format:
    {
        "name": "tool_name",
        "description": "Tool description",
        "input_schema": {
            "type": "object",
            "properties": {...},
            "required": [...]
        }
    }
    """
    tools = []

    for tool in tool_catalog:
        name = tool.get("name", "")
        description = tool.get("description", "")
        input_schema = tool.get("inputSchema", {})

        # Skip tools without proper name
        if not name:
            continue

        anthropic_tool = {
            "name": name,
            "description": description or f"Tool: {name}",
            "input_schema": input_schema if input_schema else {
                "type": "object",
                "properties": {},
                "required": []
            }
        }

        tools.append(anthropic_tool)

    return tools


class AnthropicAdapter:
    """Adapter for Anthropic Claude-based planning.

    Uses Anthropic's Claude API to analyze queries and
    generate execution plans by leveraging tool use capabilities.
    """

    def __init__(self, model_id: str, api_key: str | None):
        self.model_id = model_id
        self.api_key = api_key
        self._client = None

    def _get_client(self):
        """Lazily initialize the Anthropic client."""
        if self._client is None:
            if not self.api_key:
                raise RuntimeError("Anthropic API key not configured")

            from anthropic import Anthropic
            self._client = Anthropic(api_key=self.api_key)

        return self._client

    async def plan(self, query: str, tool_catalog: list[dict]) -> Plan:
        """Generate an execution plan using Claude's tool use.

        Args:
            query: The user's natural language query.
            tool_catalog: List of available tool definitions (MCP format).

        Returns:
            Plan object with steps to execute.
        """
        # If no API key, return empty plan
        if not self.api_key:
            return Plan(
                query=query,
                steps=[],
                notes="Anthropic planning unavailable: missing API key"
            )

        try:
            client = self._get_client()

            # Convert tool catalog to Anthropic format
            tools = _tool_catalog_to_anthropic_tools(tool_catalog)

            if not tools:
                return Plan(
                    query=query,
                    steps=[],
                    notes="No valid tools in catalog"
                )

            # Call Claude with tools
            # Using sync client but wrapping for async compatibility
            import asyncio

            def sync_call():
                return client.messages.create(
                    model=self.model_id,
                    max_tokens=4096,
                    system=PLANNING_SYSTEM_PROMPT,
                    tools=tools,
                    messages=[
                        {
                            "role": "user",
                            "content": query
                        }
                    ],
                    temperature=0.1,  # Low temperature for consistent planning
                )

            # Run sync call in executor to not block event loop
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, sync_call)

            # Parse tool use blocks from response
            steps = []
            rationale_parts = []

            for block in response.content:
                if block.type == "text":
                    rationale_parts.append(block.text)
                elif block.type == "tool_use":
                    steps.append(PlanStep(
                        tool_name=block.name,
                        arguments=block.input if isinstance(block.input, dict) else {},
                        rationale=" ".join(rationale_parts) if rationale_parts else "Claude tool call"
                    ))

            notes = "claude_tool_use"
            if rationale_parts and not steps:
                # Model provided text but no tool calls
                notes = f"no_tool_calls: {' '.join(rationale_parts)[:200]}"

            return Plan(
                query=query,
                steps=steps,
                notes=notes
            )

        except Exception as e:
            print(f"[AnthropicAdapter] Planning error: {e}", file=sys.stderr)
            return Plan(
                query=query,
                steps=[],
                notes=f"planning_error: {str(e)[:100]}"
            )


def load_anthropic_adapter(model_id: str, api_key: str | None) -> AnthropicAdapter | None:
    """Load the Anthropic adapter if anthropic SDK is available.

    Args:
        model_id: The Claude model ID to use (e.g., 'claude-opus-4-20250514').
        api_key: Anthropic API key for authentication.

    Returns:
        AnthropicAdapter instance or None if dependencies unavailable.
    """
    # Check for anthropic SDK
    try:
        import anthropic
    except ImportError:
        return None

    if not api_key:
        return None

    return AnthropicAdapter(model_id, api_key)
