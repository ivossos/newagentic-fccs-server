"""Mock data for FCCS operations - used when FCCS_MOCK_MODE=true."""

from typing import Any

MOCK_APPLICATIONS: dict[str, Any] = {
    "items": [
        {
            "name": "Delphi_app",
            "type": "FCCS",
            "description": "Mock Application for Testing"
        }
    ]
}

MOCK_JOBS: dict[str, Any] = {
    "items": [
        {
            "jobId": "101",
            "jobName": "Consolidate",
            "status": "Completed",
            "startTime": "2023-10-27T10:00:00Z",
            "endTime": "2023-10-27T10:05:00Z"
        },
        {
            "jobId": "102",
            "jobName": "Data Import",
            "status": "Running",
            "startTime": "2023-10-27T11:00:00Z"
        }
    ]
}

MOCK_JOB_STATUS: dict[str, dict[str, Any]] = {
    "101": {
        "jobId": "101",
        "jobName": "Consolidate",
        "status": "Success",
        "details": "Rule executed successfully",
        "log": "Rule 'Consolidation' completed in 2s."
    },
    "102": {
        "jobId": "102",
        "jobName": "Data Import",
        "status": "Running",
        "details": "Importing data..."
    }
}

MOCK_RULE_RESULT: dict[str, Any] = {
    "jobId": "103",
    "jobName": "Business Rule",
    "status": "Submitted",
    "details": "Rule submitted for processing."
}

MOCK_MDX_RESULT: dict[str, Any] = {
    "metadata": {
        "columns": ["Jan", "Feb", "Mar"],
        "rows": ["Sales", "COGS"]
    },
    "data": [
        [100, 110, 120],
        [40, 45, 50]
    ]
}

MOCK_DIMENSIONS: dict[str, Any] = {
    "items": [
        {"name": "Account", "type": "Account"},
        {"name": "Entity", "type": "Entity"},
        {"name": "Period", "type": "Time"},
        {"name": "Scenario", "type": "Scenario"},
        {"name": "Version", "type": "Version"},
        {"name": "Years", "type": "Time"}
    ]
}

MOCK_MEMBERS: dict[str, Any] = {
    "items": [
        {"name": "NetIncome", "description": "Net Income", "parent": "Root"},
        {"name": "Revenue", "description": "Total Revenue", "parent": "NetIncome"},
        {"name": "Expenses", "description": "Total Expenses", "parent": "NetIncome"}
    ]
}

MOCK_DATA_RULE_RESULT: dict[str, Any] = {
    "jobId": "201",
    "jobName": "Import Data",
    "status": "Submitted",
    "details": "Data load rule submitted successfully."
}

MOCK_DATA_SLICE: dict[str, Any] = {
    "pov": ["Year", "Scenario"],
    "columns": [{"2024": ["Jan"]}],
    "rows": [{"headers": ["Net Income"], "data": [1000]}]
}

# Aggregated mock data export
MOCK_DATA: dict[str, Any] = {
    "applications": MOCK_APPLICATIONS,
    "jobs": MOCK_JOBS,
    "job_status": MOCK_JOB_STATUS,
    "rule_result": MOCK_RULE_RESULT,
    "mdx_result": MOCK_MDX_RESULT,
    "dimensions": MOCK_DIMENSIONS,
    "members": MOCK_MEMBERS,
    "data_rule_result": MOCK_DATA_RULE_RESULT,
    "data_slice": MOCK_DATA_SLICE,
}
