"""Report tools - generate_report, get_report_job_status, generate_report_script."""

from typing import Any, Optional

from fccs_agent.client.fccs_client import FccsClient
from fccs_agent.reporting.script_generator import generate_report_script as _generate_report_script

_client: FccsClient = None


def set_client(client: FccsClient):
    global _client
    _client = client


async def generate_report(
    group_name: str,
    report_name: str,
    generated_report_file_name: Optional[str] = None,
    parameters: Optional[dict[str, Any]] = None,
    format: str = "PDF",
    module: str = "FCM",
    emails: Optional[str] = None,
    run_async: bool = False
) -> dict[str, Any]:
    """Generate FCCS report (Task Manager, Supplemental Data, Enterprise Journal) / Gerar relatorio FCCS.

    Args:
        group_name: Group name the report is associated with (e.g., 'Task Manager').
        report_name: Name of the report to generate.
        generated_report_file_name: User-specified name for the generated report.
        parameters: Report-specific parameters (Schedule, Period, etc.).
        format: Report format - HTML, PDF, XLSX, CSV (default: PDF).
        module: Module - FCM (Task Manager) or SDM (Supplemental Data Manager).
        emails: Comma-separated email addresses to receive the report.
        run_async: Run asynchronously (recommended for larger reports).

    Returns:
        dict: Report generation result or job ID if async.
    """
    report_params = {
        "groupName": group_name,
        "reportName": report_name,
        "format": format,
        "module": module,
        "runAsync": run_async,
    }
    if generated_report_file_name:
        report_params["generatedReportFileName"] = generated_report_file_name
    if parameters:
        report_params["parameters"] = parameters
    if emails:
        report_params["emails"] = emails

    result = await _client.generate_report(report_params)
    return {"status": "success", "data": result}


async def get_report_job_status(
    job_id: str,
    report_type: str = "FCCS"
) -> dict[str, Any]:
    """Get status of an asynchronously running report job / Obter status de um job de relatorio.

    Args:
        job_id: Job ID from async report generation.
        report_type: Report type - FCCS or SDM (default: FCCS).

    Returns:
        dict: Job status details.
    """
    result = await _client.get_report_job_status(job_id, report_type)
    return {"status": "success", "data": result}


async def generate_report_script(
    script_name: str,
    report_type: str = "HTML",
    description: str = "Custom FCCS report",
    accounts: Optional[list[str]] = None,
    entities: Optional[list[str]] = None,
    periods: Optional[list[str]] = None,
    years: Optional[list[str]] = None,
    scenarios: Optional[list[str]] = None
) -> dict[str, Any]:
    """Generate a Python script template for custom FCCS reporting / Gerar script Python para relatorio customizado.

    Args:
        script_name: Name of the script file (without .py extension).
        report_type: Type of report - HTML, PDF, or CSV (default: HTML).
        description: Description of what the report does.
        accounts: List of account names to query.
        entities: List of entity names to query.
        periods: List of periods to query (e.g., ['Jan', 'Feb', 'Dec']).
        years: List of years to query (e.g., ['FY24', 'FY25']).
        scenarios: List of scenarios to query (e.g., ['Actual', 'Budget']).

    Returns:
        dict: Path to generated script and summary.
    """
    return _generate_report_script(
        script_name=script_name,
        report_type=report_type,
        description=description,
        accounts=accounts,
        entities=entities,
        periods=periods,
        years=years,
        scenarios=scenarios
    )


TOOL_DEFINITIONS = [
    {
        "name": "generate_report",
        "description": "Generate FCCS report (Task Manager, Supplemental Data, Enterprise Journal) / Gerar relatorio FCCS",
        "inputSchema": {
            "type": "object",
            "properties": {
                "group_name": {
                    "type": "string",
                    "description": "Group name the report is associated with (e.g., 'Task Manager')",
                },
                "report_name": {
                    "type": "string",
                    "description": "Name of the report to generate",
                },
                "generated_report_file_name": {
                    "type": "string",
                    "description": "User-specified name for the generated report",
                },
                "parameters": {
                    "type": "object",
                    "description": "Report-specific parameters (Schedule, Period, etc.)",
                },
                "format": {
                    "type": "string",
                    "enum": ["HTML", "PDF", "XLSX", "CSV"],
                    "description": "Report format (default: PDF)",
                },
                "module": {
                    "type": "string",
                    "enum": ["FCM", "SDM"],
                    "description": "Module: FCM (Task Manager) or SDM (Supplemental Data Manager)",
                },
                "emails": {
                    "type": "string",
                    "description": "Comma-separated email addresses to receive the report",
                },
                "run_async": {
                    "type": "boolean",
                    "description": "Run asynchronously (recommended for larger reports)",
                },
            },
            "required": ["group_name", "report_name"],
        },
    },
    {
        "name": "get_report_job_status",
        "description": "Get status of an asynchronously running report job / Obter status de um job de relatorio",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": "Job ID from async report generation",
                },
                "report_type": {
                    "type": "string",
                    "enum": ["FCCS", "SDM"],
                    "description": "Report type (default: FCCS)",
                },
            },
            "required": ["job_id"],
        },
    },
    {
        "name": "generate_report_script",
        "description": "Generate a Python script template for custom FCCS reporting / Gerar script Python para relatorio customizado",
        "inputSchema": {
            "type": "object",
            "properties": {
                "script_name": {
                    "type": "string",
                    "description": "Name of the script file (without .py extension)",
                },
                "report_type": {
                    "type": "string",
                    "enum": ["HTML", "PDF", "CSV"],
                    "description": "Type of report (default: HTML)",
                },
                "description": {
                    "type": "string",
                    "description": "Description of what the report does",
                },
                "accounts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of account names to query",
                },
                "entities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of entity names to query",
                },
                "periods": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of periods to query (e.g., ['Jan', 'Feb', 'Dec'])",
                },
                "years": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of years to query (e.g., ['FY24', 'FY25'])",
                },
                "scenarios": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of scenarios to query (e.g., ['Actual', 'Budget'])",
                },
            },
            "required": ["script_name"],
        },
    },
]
