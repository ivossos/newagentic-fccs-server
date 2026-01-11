from __future__ import annotations

import inspect
from contextlib import asynccontextmanager
from typing import Any, Annotated

from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field
from pydantic.json_schema import WithJsonSchema

from fccs_agent.agent import AGENT_INSTRUCTION, execute_tool, get_tool_definitions
from fccs_agent.config import config
from fccs_agent.runtime import ensure_initialized, get_session_id, record_tool_result, shutdown


def build_fastmcp_server() -> FastMCP:
    server = FastMCP(
        name="fccs-fastmcp-agent",
        instructions=AGENT_INSTRUCTION,
        host=config.fastmcp_host,
        port=config.fastmcp_port,
        streamable_http_path="/mcp",
        lifespan=_lifespan,
    )

    for tool_def in get_tool_definitions():
        fn = _make_tool_function(tool_def)
        server.add_tool(
            fn,
            name=tool_def["name"],
            description=tool_def.get("description", ""),
        )

    return server


@asynccontextmanager
async def _lifespan(_: FastMCP):
    try:
        yield
    finally:
        await shutdown()


def _make_tool_function(tool_def: dict[str, Any]):
    tool_name = tool_def["name"]
    input_schema = tool_def.get("inputSchema", {})

    async def tool_func(ctx: Context, **kwargs: Any) -> dict[str, Any]:
        await ensure_initialized()
        session_id = get_session_id(ctx)
        user_query = kwargs.get("query", "")
        result = await execute_tool(tool_name, kwargs, session_id=session_id, user_query=user_query)
        record_tool_result(session_id, result)
        return result

    tool_func.__name__ = tool_name
    tool_func.__doc__ = tool_def.get("description", "")
    tool_func.__signature__ = _build_signature(input_schema)
    return tool_func


def _build_signature(input_schema: dict[str, Any]) -> inspect.Signature:
    props = input_schema.get("properties", {})
    required = set(input_schema.get("required", []))
    ordered_names = [name for name in props if name in required]
    ordered_names.extend([name for name in props if name not in required])

    params = [
        inspect.Parameter(
            "ctx",
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            annotation=Context,
        )
    ]

    for name in ordered_names:
        spec = props[name]
        annotation = _annotation_for_schema(spec)
        if name in required:
            default = inspect._empty
        else:
            default = spec.get("default", None)

        params.append(
            inspect.Parameter(
                name,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=default,
                annotation=annotation,
            )
        )

    return inspect.Signature(params)


def _annotation_for_schema(spec: dict[str, Any]) -> Any:
    json_type = spec.get("type", "string")
    py_type = _map_json_type(json_type)

    metadata: list[Any] = []
    if "description" in spec:
        metadata.append(Field(description=spec["description"]))

    metadata.append(WithJsonSchema(spec))

    if metadata:
        return Annotated[(py_type, *metadata)]

    return py_type


def _map_json_type(json_type: str) -> Any:
    if json_type == "string":
        return str
    if json_type == "number":
        return float
    if json_type == "integer":
        return int
    if json_type == "boolean":
        return bool
    if json_type == "array":
        return list
    if json_type == "object":
        return dict
    return str
