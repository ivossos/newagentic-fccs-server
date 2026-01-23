"""Personalization tools for onboarding and preferences."""

from typing import Any, Optional

from fccs_agent.services.personalization_service import get_personalization_service


async def get_personalization_status(
    session_id: str = "default",
    org_id: Optional[str] = None
) -> dict[str, Any]:
    """Get personalization checklist status."""
    service = get_personalization_service()
    if not service:
        return {"status": "error", "error": "Personalization service not available"}

    status = service.get_status(session_id=session_id, org_id=org_id)
    if not status:
        status = service.ensure_checklist(session_id=session_id, org_id=org_id)

    return {"status": "success", "data": status.to_dict()}


async def update_personalization_item(
    key: str,
    status: str = "done",
    value: Optional[str] = None,
    note: Optional[str] = None,
    session_id: str = "default",
    org_id: Optional[str] = None
) -> dict[str, Any]:
    """Update a personalization checklist item."""
    service = get_personalization_service()
    if not service:
        return {"status": "error", "error": "Personalization service not available"}

    updated = service.update_item(
        session_id=session_id,
        org_id=org_id,
        key=key,
        status=status,
        value=value,
        note=note
    )
    if not updated:
        return {"status": "error", "error": "Failed to update checklist item"}

    return {"status": "success", "data": updated.to_dict()}


async def set_personalization_preference(
    key: str,
    value: Any,
    session_id: str = "default",
    org_id: Optional[str] = None
) -> dict[str, Any]:
    """Set a personalization preference.

    Common preference keys:
    - app_name: Application name
    - default_cube: Default cube/plan type for queries
    - pov_defaults: Default POV settings (dict)
    - language: Preferred language
    - date_format: Date format preference
    - number_format: Number format preference
    - export_format: Default export format (docx, xlsx, pdf)

    Args:
        key: Preference identifier
        value: Preference value (can be string, number, dict, list)
        session_id: Session identifier (default: 'default')
        org_id: Optional organization identifier

    Returns:
        dict: Success status with updated checklist state.
    """
    service = get_personalization_service()
    if not service:
        return {"status": "error", "error": "Personalization service not available"}

    updated = service.set_preference(
        session_id=session_id,
        org_id=org_id,
        key=key,
        value=value
    )
    if not updated:
        return {"status": "error", "error": "Failed to set preference"}

    return {"status": "success", "data": updated.to_dict()}


async def get_personalization_preferences(
    session_id: str = "default",
    org_id: Optional[str] = None
) -> dict[str, Any]:
    """Get all user preferences.

    Args:
        session_id: Session identifier (default: 'default')
        org_id: Optional organization identifier

    Returns:
        dict: All user preferences.
    """
    service = get_personalization_service()
    if not service:
        return {"status": "error", "error": "Personalization service not available"}

    try:
        preferences = service.get_all_preferences(
            session_id=session_id,
            org_id=org_id
        )
        return {
            "status": "success",
            "data": preferences
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


TOOL_DEFINITIONS = [
    {
        "name": "get_personalization_status",
        "description": "Get the current personalization/onboarding checklist status showing progress on configuring preferences / Obter status do checklist de personalizacao",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Session identifier (default: 'default')",
                },
                "org_id": {
                    "type": "string",
                    "description": "Organization identifier (optional)",
                },
            },
        },
    },
    {
        "name": "update_personalization_item",
        "description": "Update a personalization checklist item (app_name, cube, pov_defaults, dimensions, language, reporting) / Atualizar item do checklist de personalizacao",
        "inputSchema": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "The checklist item key (app_name, cube, pov_defaults, dimensions, language, reporting)",
                },
                "status": {
                    "type": "string",
                    "description": "Item status (default: 'done')",
                },
                "value": {
                    "type": "string",
                    "description": "The value/response for the item",
                },
                "note": {
                    "type": "string",
                    "description": "Optional note for the item",
                },
                "session_id": {
                    "type": "string",
                    "description": "Session identifier (default: 'default')",
                },
                "org_id": {
                    "type": "string",
                    "description": "Organization identifier (optional)",
                },
            },
            "required": ["key"],
        },
    },
    {
        "name": "set_personalization_preference",
        "description": "Set a user preference (app_name, default_cube, pov_defaults, language, export_format, etc.) / Definir preferencia do usuario",
        "inputSchema": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "Preference identifier",
                },
                "value": {
                    "description": "Preference value (string, number, dict, or list)",
                },
                "session_id": {
                    "type": "string",
                    "description": "Session identifier (default: 'default')",
                },
                "org_id": {
                    "type": "string",
                    "description": "Organization identifier (optional)",
                },
            },
            "required": ["key", "value"],
        },
    },
    {
        "name": "get_personalization_preferences",
        "description": "Get all user preferences / Obter todas as preferencias do usuario",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Session identifier (default: 'default')",
                },
                "org_id": {
                    "type": "string",
                    "description": "Organization identifier (optional)",
                },
            },
        },
    },
]
