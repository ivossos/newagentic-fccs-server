"""Application tools - get_application_info, get_rest_api_version."""

from typing import Any

from fccs_agent.client.fccs_client import FccsClient

# Global client reference - set by agent.py
_client: FccsClient = None


def set_client(client: FccsClient):
    """Set the FCCS client instance."""
    global _client
    _client = client


async def get_application_info() -> dict[str, Any]:
    """Get information about the FCCS application / Obter informacoes sobre a aplicacao FCCS.

    Returns:
        dict: Application details including name, type, and description.
    """
    apps = await _client.get_applications()
    return {"status": "success", "data": apps}


async def get_rest_api_version() -> dict[str, Any]:
    """Get the REST API version / Obter a versao da API REST.

    Returns:
        dict: API version information.
    """
    version = await _client.get_rest_api_version()
    return {"status": "success", "data": version}


# Tool definitions for MCP server
TOOL_DEFINITIONS = [
    {
        "name": "get_application_info",
        "description": "Get information about the FCCS application / Obter informacoes sobre a aplicacao FCCS",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_rest_api_version",
        "description": "Get the REST API version / Obter a versao da API REST",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
]
