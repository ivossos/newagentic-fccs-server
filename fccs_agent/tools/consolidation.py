"""Consolidation tools - rulesets, metadata, ICP reports, supplemental data."""

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


async def export_consolidation_rulesets(
    parameters: Optional[dict[str, Any]] = None
) -> dict[str, Any]:
    """Export configurable consolidation rulesets / Exportar regras de consolidacao.

    Args:
        parameters: Export parameters (ruleNames, rulesetNames, etc.).

    Returns:
        dict: Job submission result.
    """
    result = await _client.export_consolidation_rulesets(_app_name, parameters)
    return {"status": "success", "data": result}


async def import_consolidation_rulesets(
    parameters: Optional[dict[str, Any]] = None
) -> dict[str, Any]:
    """Import configurable consolidation rulesets / Importar regras de consolidacao.

    Args:
        parameters: Import parameters.

    Returns:
        dict: Job submission result.
    """
    result = await _client.import_consolidation_rulesets(_app_name, parameters)
    return {"status": "success", "data": result}


async def validate_metadata(
    log_file_name: Optional[str] = None
) -> dict[str, Any]:
    """Validate application metadata / Validar metadados da aplicacao.

    Args:
        log_file_name: Optional log file name for results.

    Returns:
        dict: Validation results.
    """
    result = await _client.validate_metadata(_app_name, log_file_name)
    return {"status": "success", "data": result}


async def generate_intercompany_matching_report(
    parameters: Optional[dict[str, Any]] = None
) -> dict[str, Any]:
    """Generate intercompany matching report / Gerar relatorio de correspondencia ICP.

    Args:
        parameters: Report parameters (scenario, year, period, etc.).

    Returns:
        dict: Job submission result.
    """
    result = await _client.generate_intercompany_matching_report(_app_name, parameters)
    return {"status": "success", "data": result}


async def import_supplementation_data(
    parameters: Optional[dict[str, Any]] = None
) -> dict[str, Any]:
    """Import supplementation data / Importar dados de suplementacao.

    Args:
        parameters: Import parameters (period, year, scenario, etc.).

    Returns:
        dict: Job submission result.
    """
    result = await _client.import_supplementation_data(_app_name, parameters)
    return {"status": "success", "data": result}


async def deploy_form_template(
    template_name: str,
    parameters: Optional[dict[str, Any]] = None
) -> dict[str, Any]:
    """Deploy a form template / Implantar um template de formulario.

    Args:
        template_name: Name of the form template to deploy.
        parameters: Deployment parameters.

    Returns:
        dict: Deployment result.
    """
    result = await _client.deploy_form_template(_app_name, template_name, parameters)
    return {"status": "success", "data": result}


async def generate_consolidation_process_report(
    entity: str = "FCCS_Total Geography",
    account: str = "FCCS_Net Income",
    period: str = "Jan",
    year: str = "FY24",
    scenario: str = "Actual"
) -> dict[str, Any]:
    """Generate a Consolidation Process Overview Report / Gerar relatorio de processo de consolidacao.

    Args:
        entity: The Entity member.
        account: The Account member.
        period: The Period member.
        year: The Year member.
        scenario: The Scenario member.

    Returns:
        dict: Report generation summary and path.
    """
    from scripts.consolidation_process_report import get_consolidation_data, generate_html_report
    
    data = await get_consolidation_data(entity, account, period, year, scenario)
    report_path = generate_html_report(entity, account, period, year, scenario, data)
    
    return {
        "status": "success",
        "data": {
            "report_path": report_path,
            "entity": entity,
            "account": account,
            "message": f"Consolidation process report generated for {entity}"
        }
    }


TOOL_DEFINITIONS = [
    {
        "name": "export_consolidation_rulesets",
        "description": "Export configurable consolidation rulesets / Exportar regras de consolidacao",
        "inputSchema": {
            "type": "object",
            "properties": {
                "parameters": {
                    "type": "object",
                    "description": "Export parameters (ruleNames, rulesetNames, etc.)",
                },
            },
        },
    },
    {
        "name": "import_consolidation_rulesets",
        "description": "Import configurable consolidation rulesets / Importar regras de consolidacao",
        "inputSchema": {
            "type": "object",
            "properties": {
                "parameters": {
                    "type": "object",
                    "description": "Import parameters",
                },
            },
        },
    },
    {
        "name": "validate_metadata",
        "description": "Validate application metadata / Validar metadados da aplicacao",
        "inputSchema": {
            "type": "object",
            "properties": {
                "log_file_name": {
                    "type": "string",
                    "description": "Optional log file name for results",
                },
            },
        },
    },
    {
        "name": "generate_intercompany_matching_report",
        "description": "Generate intercompany matching report / Gerar relatorio de correspondencia ICP",
        "inputSchema": {
            "type": "object",
            "properties": {
                "parameters": {
                    "type": "object",
                    "description": "Report parameters (scenario, year, period, etc.)",
                },
            },
        },
    },
    {
        "name": "import_supplementation_data",
        "description": "Import supplementation data / Importar dados de suplementacao",
        "inputSchema": {
            "type": "object",
            "properties": {
                "parameters": {
                    "type": "object",
                    "description": "Import parameters (period, year, scenario, etc.)",
                },
            },
        },
    },
    {
        "name": "deploy_form_template",
        "description": "Deploy a form template / Implantar um template de formulario",
        "inputSchema": {
            "type": "object",
            "properties": {
                "template_name": {
                    "type": "string",
                    "description": "Name of the form template to deploy",
                },
                "parameters": {
                    "type": "object",
                    "description": "Deployment parameters",
                },
            },
            "required": ["template_name"],
        },
    },
    {
        "name": "generate_consolidation_process_report",
        "description": "Generate a Consolidation Process Overview Report showing data flow from Local GAAP to Consolidated / Gerar relatorio de processo de consolidacao",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity": {
                    "type": "string",
                    "description": "The Entity member (default: 'FCCS_Total Geography')",
                },
                "account": {
                    "type": "string",
                    "description": "The Account member (default: 'FCCS_Net Income')",
                },
                "period": {
                    "type": "string",
                    "description": "The Period member (default: 'Jan')",
                },
                "year": {
                    "type": "string",
                    "description": "The Year member (default: 'FY24')",
                },
                "scenario": {
                    "type": "string",
                    "description": "The Scenario member (default: 'Actual')",
                },
            },
        },
    },
]
