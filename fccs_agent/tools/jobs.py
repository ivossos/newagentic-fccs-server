"""Job tools - list_jobs, get_job_status, run_business_rule, run_data_rule."""

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


async def list_jobs() -> dict[str, Any]:
    """List recent jobs in the FCCS application / Listar jobs recentes na aplicacao FCCS.

    Returns:
        dict: List of recent jobs with status information.
    """
    jobs = await _client.list_jobs(_app_name)
    return {"status": "success", "data": jobs}


async def get_job_status(job_id: str) -> dict[str, Any]:
    """Get the status of a specific job / Obter o status de um job especifico.

    Args:
        job_id: The ID of the job to check.

    Returns:
        dict: Job status details.
    """
    status = await _client.get_job_status(_app_name, job_id)
    return {"status": "success", "data": status}


async def run_business_rule(
    rule_name: str,
    parameters: Optional[dict[str, Any]] = None
) -> dict[str, Any]:
    """Run a business rule (e.g., Consolidation) / Executar regra de negocio.

    Args:
        rule_name: The name of the business rule to run.
        parameters: Optional parameters for the rule.

    Returns:
        dict: Job submission result.
    """
    result = await _client.run_business_rule(_app_name, rule_name, parameters)
    return {"status": "success", "data": result}


async def run_data_rule(
    rule_name: str,
    start_period: str,
    end_period: str,
    import_mode: str = "REPLACE",
    export_mode: str = "STORE_DATA"
) -> dict[str, Any]:
    """Run a Data Management load rule / Executar regra de carga do Data Management.

    Args:
        rule_name: The name of the data load rule.
        start_period: Start period (e.g., 'Jan-23').
        end_period: End period (e.g., 'Jan-23').
        import_mode: Import mode (default: REPLACE).
        export_mode: Export mode (default: STORE_DATA).

    Returns:
        dict: Job submission result.
    """
    result = await _client.run_data_rule(
        _app_name, rule_name, start_period, end_period, import_mode, export_mode
    )
    return {"status": "success", "data": result}


TOOL_DEFINITIONS = [
    {
        "name": "list_jobs",
        "description": "List recent jobs in the FCCS application / Listar jobs recentes na aplicacao FCCS",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_job_status",
        "description": "Get the status of a specific job / Obter o status de um job especifico",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": "The ID of the job to check / O ID do job para verificar",
                },
            },
            "required": ["job_id"],
        },
    },
    {
        "name": "run_business_rule",
        "description": "Run a business rule (e.g., Consolidation) / Executar regra de negocio",
        "inputSchema": {
            "type": "object",
            "properties": {
                "rule_name": {
                    "type": "string",
                    "description": "The name of the business rule to run",
                },
                "parameters": {
                    "type": "object",
                    "description": "Optional parameters for the rule",
                },
            },
            "required": ["rule_name"],
        },
    },
    {
        "name": "run_data_rule",
        "description": "Run a Data Management load rule / Executar regra de carga do Data Management",
        "inputSchema": {
            "type": "object",
            "properties": {
                "rule_name": {
                    "type": "string",
                    "description": "The name of the data load rule",
                },
                "start_period": {
                    "type": "string",
                    "description": "Start period (e.g., 'Jan-23')",
                },
                "end_period": {
                    "type": "string",
                    "description": "End period (e.g., 'Jan-23')",
                },
                "import_mode": {
                    "type": "string",
                    "description": "Import mode (default: REPLACE)",
                },
                "export_mode": {
                    "type": "string",
                    "description": "Export mode (default: STORE_DATA)",
                },
            },
            "required": ["rule_name", "start_period", "end_period"],
        },
    },
]
