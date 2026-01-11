"""Journal tools - get_journals, get_journal_details, perform_journal_action, etc."""

from typing import Any, Optional

from fccs_agent.client.fccs_client import FccsClient

_client: FccsClient = None
_app_name: str = None


def set_client(client: FccsClient):
    global _client
    _client = client


def set_app_name(app_name: str):
    global _app_name
    _app_name = app_name


async def get_journals(
    scenario: str,
    year: str,
    period: str,
    consolidation: str = "FCCS_Entity Input",
    view: str = "FCCS_Periodic",
    status: str = "Posted",
    offset: int = 0,
    limit: int = 100
) -> dict[str, Any]:
    """Retrieve consolidation journals with filters / Obter diarios de consolidacao.

    Note: FCCS REST API requires scenario, year, period, consolidation, view, and status.

    Args:
        scenario: Filter by scenario (required, e.g., 'Actual').
        year: Filter by year (required, e.g., 'FY25').
        period: Filter by period (required, e.g., 'Jan', 'Feb', 'Mar').
        consolidation: Filter by consolidation member (default: 'FCCS_Entity Input').
        view: Filter by view (default: 'FCCS_Periodic').
        status: Filter by status (default: 'Posted'). Valid: 'Working', 'Submitted', 'Approved', 'Rejected', 'Posted'.
        offset: Offset for pagination (default: 0).
        limit: Limit results (default: 100).

    Returns:
        dict: List of journals.
    """
    filters = {
        "scenario": scenario,
        "year": year,
        "period": period,
        "consolidation": consolidation,
        "view": view,
        "status": status,
    }

    journals = await _client.get_journals(
        _app_name, filters, offset, limit
    )
    return {"status": "success", "data": journals}


async def get_journal_details(
    journal_label: str,
    scenario: Optional[str] = None,
    year: Optional[str] = None,
    period: Optional[str] = None,
    line_items: bool = True
) -> dict[str, Any]:
    """Get detailed information about a specific journal / Obter detalhes de um diario.

    Args:
        journal_label: The journal label.
        scenario: Filter by scenario.
        year: Filter by year.
        period: Filter by period.
        line_items: Include line items (default: true).

    Returns:
        dict: Journal details.
    """
    filters = {}
    if scenario:
        filters["scenario"] = scenario
    if year:
        filters["year"] = year
    if period:
        filters["period"] = period

    details = await _client.get_journal_details(
        _app_name, journal_label, filters if filters else None, line_items
    )
    return {"status": "success", "data": details}


async def perform_journal_action(
    journal_label: str,
    action: str,
    scenario: str,
    year: str,
    period: str,
    consolidation: str = "FCCS_Entity Input",
    comment: Optional[str] = None
) -> dict[str, Any]:
    """Perform an action on a journal (SUBMIT, APPROVE, REJECT, POST, UNPOST) / Executar acao em um diario.

    Based on Oracle FCCS REST API - Perform Journal Actions for Financial Consolidation and Close.
    
    Args:
        journal_label: The journal label (e.g., 'FY25Mar Contingent Consideration Adj').
        action: Action to perform - must be one of: SUBMIT, APPROVE, REJECT, POST, UNPOST.
        scenario: Scenario name (required, e.g., 'Actual').
        year: Year (required, e.g., 'FY25').
        period: Period (required, e.g., 'Jan', 'Feb', 'Mar', etc.).
        consolidation: Consolidation member (default: 'FCCS_Entity Input').
        comment: Optional comment for the action.

    Returns:
        dict: Action result with status.
        
    Example:
        perform_journal_action(
            journal_label="FY25Mar Contingent Consideration Adj",
            action="POST",
            scenario="Actual",
            year="FY25",
            period="Mar"
        )
    """
    result = await _client.perform_journal_action(
        _app_name,
        journal_label,
        action,
        scenario,
        year,
        period,
        consolidation,
        comment
    )
    
    # Check if the result indicates an error
    if isinstance(result, dict) and result.get("status") == "error":
        return result
    
    return {"status": "success", "data": result}


async def update_journal_period(
    journal_label: str,
    new_period: str,
    parameters: Optional[dict[str, Any]] = None
) -> dict[str, Any]:
    """Update the period of a journal / Atualizar o periodo de um diario.

    Args:
        journal_label: The journal label.
        new_period: New period to set.
        parameters: Additional parameters.

    Returns:
        dict: Update result.
    """
    result = await _client.update_journal_period(
        _app_name, journal_label, new_period, parameters
    )
    return {"status": "success", "data": result}


async def export_journals(
    parameters: Optional[dict[str, Any]] = None
) -> dict[str, Any]:
    """Export consolidation journals / Exportar diarios de consolidacao.

    Args:
        parameters: Export parameters (scenario, year, period, etc.).

    Returns:
        dict: Job submission result.
    """
    result = await _client.export_journals(_app_name, parameters)
    return {"status": "success", "data": result}


async def import_journals(
    parameters: Optional[dict[str, Any]] = None
) -> dict[str, Any]:
    """Import consolidation journals / Importar diarios de consolidacao.

    Args:
        parameters: Import parameters.

    Returns:
        dict: Job submission result.
    """
    result = await _client.import_journals(_app_name, parameters)
    return {"status": "success", "data": result}


TOOL_DEFINITIONS = [
    {
        "name": "get_journals",
        "description": "Retrieve consolidation journals with optional filters / Obter diarios de consolidacao",
        "inputSchema": {
            "type": "object",
            "properties": {
                "scenario": {"type": "string", "description": "Filter by scenario (required, e.g., 'Actual')"},
                "year": {"type": "string", "description": "Filter by year (required, e.g., 'FY25')"},
                "period": {"type": "string", "description": "Filter by period (required, e.g., 'Jan', 'Feb', 'Mar')"},
                "consolidation": {"type": "string", "description": "Filter by consolidation member (default: 'FCCS_Entity Input')", "default": "FCCS_Entity Input"},
                "view": {"type": "string", "description": "Filter by view (default: 'FCCS_Periodic')", "default": "FCCS_Periodic"},
                "status": {"type": "string", "description": "Filter by status (default: 'Posted'). Valid: 'Working', 'Submitted', 'Approved', 'Rejected', 'Posted'", "default": "Posted"},
                "offset": {"type": "number", "description": "Offset for pagination (default: 0)"},
                "limit": {"type": "number", "description": "Limit results (default: 100)"},
            },
            "required": ["scenario", "year", "period"],
        },
    },
    {
        "name": "get_journal_details",
        "description": "Get detailed information about a specific journal / Obter detalhes de um diario",
        "inputSchema": {
            "type": "object",
            "properties": {
                "journal_label": {"type": "string", "description": "The journal label"},
                "scenario": {"type": "string", "description": "Filter by scenario"},
                "year": {"type": "string", "description": "Filter by year"},
                "period": {"type": "string", "description": "Filter by period"},
                "line_items": {"type": "boolean", "description": "Include line items (default: true)"},
            },
            "required": ["journal_label"],
        },
    },
    {
        "name": "perform_journal_action",
        "description": "Perform an action on a journal (SUBMIT, APPROVE, REJECT, POST, UNPOST). Based on Oracle FCCS REST API - requires scenario, year, period parameters. / Executar acao em um diario",
        "inputSchema": {
            "type": "object",
            "properties": {
                "journal_label": {
                    "type": "string",
                    "description": "The journal label (e.g., 'FY25Mar Contingent Consideration Adj')"
                },
                "action": {
                    "type": "string",
                    "description": "Action to perform - must be one of: SUBMIT, APPROVE, REJECT, POST, UNPOST",
                    "enum": ["SUBMIT", "APPROVE", "REJECT", "POST", "UNPOST"]
                },
                "scenario": {
                    "type": "string",
                    "description": "Scenario name (required, e.g., 'Actual')"
                },
                "year": {
                    "type": "string",
                    "description": "Year (required, e.g., 'FY25')"
                },
                "period": {
                    "type": "string",
                    "description": "Period (required, e.g., 'Jan', 'Feb', 'Mar')"
                },
                "consolidation": {
                    "type": "string",
                    "description": "Consolidation member (default: 'FCCS_Entity Input')",
                    "default": "FCCS_Entity Input"
                },
                "comment": {
                    "type": "string",
                    "description": "Optional comment for the action"
                },
            },
            "required": ["journal_label", "action", "scenario", "year", "period"],
        },
    },
    {
        "name": "update_journal_period",
        "description": "Update the period of a journal / Atualizar o periodo de um diario",
        "inputSchema": {
            "type": "object",
            "properties": {
                "journal_label": {"type": "string", "description": "The journal label"},
                "new_period": {"type": "string", "description": "New period to set"},
                "parameters": {"type": "object", "description": "Additional parameters"},
            },
            "required": ["journal_label", "new_period"],
        },
    },
    {
        "name": "export_journals",
        "description": "Export consolidation journals / Exportar diarios de consolidacao",
        "inputSchema": {
            "type": "object",
            "properties": {
                "parameters": {"type": "object", "description": "Export parameters"},
            },
        },
    },
    {
        "name": "import_journals",
        "description": "Import consolidation journals / Importar diarios de consolidacao",
        "inputSchema": {
            "type": "object",
            "properties": {
                "parameters": {"type": "object", "description": "Import parameters"},
            },
        },
    },
]
