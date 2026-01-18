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
    """Set a personalization preference."""
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


TOOL_DEFINITIONS = [
    {
        "name": "get_personalization_status",
        "description": "Get onboarding checklist and personalization status.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "default": "default"},
                "org_id": {"type": "string"},
            },
        },
    },
    {
        "name": "update_personalization_item",
        "description": "Update a checklist item (mark done, add value/note).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "key": {"type": "string"},
                "status": {"type": "string", "default": "done"},
                "value": {"type": "string"},
                "note": {"type": "string"},
                "session_id": {"type": "string", "default": "default"},
                "org_id": {"type": "string"},
            },
            "required": ["key"],
        },
    },
    {
        "name": "set_personalization_preference",
        "description": "Set a personalization preference value.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "key": {"type": "string"},
                "value": {},
                "session_id": {"type": "string", "default": "default"},
                "org_id": {"type": "string"},
            },
            "required": ["key", "value"],
        },
    },
]
