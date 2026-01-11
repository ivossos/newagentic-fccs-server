"""Dimension tools - get_dimensions, get_members, get_dimension_hierarchy."""

from typing import Any, Optional

from fccs_agent.client.fccs_client import FccsClient
from fccs_agent.services.cache_service import get_cache_service

_client: FccsClient = None
_app_name: str = None


def set_client(client: FccsClient):
    global _client
    _client = client


def set_app_name(app_name: str):
    global _app_name
    _app_name = app_name


async def get_dimensions() -> dict[str, Any]:
    """Get list of dimensions in the application / Obter lista de dimensoes na aplicacao.

    Returns:
        dict: List of dimensions with their types.
    """
    dimensions = await _client.get_dimensions(_app_name)
    return {"status": "success", "data": dimensions}


async def get_members(dimension_name: str) -> dict[str, Any]:
    """Get members of a specific dimension / Obter membros de uma dimensao especifica.

    Args:
        dimension_name: The name of the dimension.

    Returns:
        dict: List of dimension members.
    """
    cache = get_cache_service()
    cache_key = f"members:{dimension_name}"
    
    if cache:
        cached_data = cache.get(cache_key)
        if cached_data:
            return {"status": "success", "data": cached_data, "source": "cache"}

    members = await _client.get_members(_app_name, dimension_name)
    
    if cache and members:
        cache.set(cache_key, members, ttl_seconds=86400)  # Cache for 24 hours
        
    return {"status": "success", "data": members, "source": "fccs"}


async def get_dimension_hierarchy(
    dimension_name: str,
    member_name: Optional[str] = None,
    depth: int = 5,
    include_metadata: bool = False
) -> dict[str, Any]:
    """Build a parent-child hierarchy for a dimension / Construir hierarquia pai-filho de uma dimensao.

    Args:
        dimension_name: Dimension to explore.
        member_name: Start from a specific member (optional).
        depth: Depth limit for the hierarchy (default: 5).
        include_metadata: Include raw metadata for each node.

    Returns:
        dict: Hierarchy tree structure.
    """
    cache = get_cache_service()
    cache_key = f"hierarchy:{dimension_name}:{member_name}:{depth}:{include_metadata}"
    
    if cache:
        cached_data = cache.get(cache_key)
        if cached_data:
            return {"status": "success", "data": cached_data, "source": "cache"}

    hierarchy = await _client.get_dimension_hierarchy(
        _app_name, dimension_name, member_name, depth, include_metadata
    )
    
    if cache and hierarchy:
        cache.set(cache_key, hierarchy, ttl_seconds=3600)  # Cache for 1 hour
        
    return {"status": "success", "data": hierarchy, "source": "fccs"}


TOOL_DEFINITIONS = [
    {
        "name": "get_dimensions",
        "description": "Get list of dimensions in the application / Obter lista de dimensoes na aplicacao",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_members",
        "description": "Get members of a specific dimension / Obter membros de uma dimensao especifica",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dimension_name": {
                    "type": "string",
                    "description": "The name of the dimension",
                },
            },
            "required": ["dimension_name"],
        },
    },
    {
        "name": "get_dimension_hierarchy",
        "description": "Build a parent-child hierarchy for a dimension / Construir hierarquia pai-filho",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dimension_name": {
                    "type": "string",
                    "description": "Dimension to explore",
                },
                "member_name": {
                    "type": "string",
                    "description": "Start from a specific member (optional)",
                },
                "depth": {
                    "type": "number",
                    "description": "Depth limit for the hierarchy (default: 5)",
                },
                "include_metadata": {
                    "type": "boolean",
                    "description": "Include raw metadata for each node",
                },
            },
            "required": ["dimension_name"],
        },
    },
]
