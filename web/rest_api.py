"""REST API for ChatGPT Actions integration."""

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from fccs_agent.agent import (
    initialize_agent,
    execute_tool,
    get_tool_definitions,
    agentic_query,
    close_agent,
)
from fccs_agent.config import config


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize agent on startup, cleanup on shutdown."""
    await initialize_agent()
    yield
    await close_agent()


app = FastAPI(
    title="FCCS Agent API",
    description="REST API for Oracle FCCS operations - Compatible with ChatGPT Actions",
    version="1.0.0",
    lifespan=lifespan,
    servers=[{"url": "https://fccs-agent-241840460713.us-central1.run.app"}],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request/Response Models
class QueryRequest(BaseModel):
    query: str = Field(..., description="Natural language query about FCCS data")
    session_id: str = Field(default="default", description="Session ID for context")


class QueryResponse(BaseModel):
    status: str
    data: Optional[dict] = None
    error: Optional[str] = None


class ToolRequest(BaseModel):
    tool_name: str = Field(..., description="Name of the tool to execute")
    arguments: dict = Field(default_factory=dict, description="Tool arguments")
    session_id: str = Field(default="default", description="Session ID")


class DataSliceRequest(BaseModel):
    accounts: list[str] = Field(..., description="Account members (e.g., ['4110', '4120'])")
    entities: list[str] = Field(default=["FCCS_Total Geography"], description="Entity members")
    periods: list[str] = Field(default=["Jan"], description="Period members")
    years: list[str] = Field(default=["FY24"], description="Year members")
    scenarios: list[str] = Field(default=["Actual"], description="Scenario members")
    currencies: list[str] = Field(default=["USD"], description="Currency members")
    session_id: str = Field(default="default")


class SmartRetrieveRequest(BaseModel):
    account: str = Field(..., description="Account member (e.g., '4110' or 'Total Revenues')")
    entity: str = Field(default="FCCS_Total Geography", description="Entity member")
    period: str = Field(default="Jan", description="Period (e.g., 'Jan', 'Feb', 'Q1')")
    years: str = Field(default="FY24", description="Year (e.g., 'FY24', 'FY23')")
    scenario: str = Field(default="Actual", description="Scenario (e.g., 'Actual', 'Budget')")
    consolidation: str = Field(default="FCCS_Entity Total", description="Consolidation member")
    session_id: str = Field(default="default")


class ConsolidationBreakdownRequest(BaseModel):
    account: str = Field(..., description="Account to analyze")
    entity: str = Field(default="FCCS_Total Geography")
    period: str = Field(default="Jan")
    years: str = Field(default="FY24")
    scenario: str = Field(default="Actual")
    session_id: str = Field(default="default")


class MovementAnalysisRequest(BaseModel):
    account: str = Field(..., description="Account to analyze")
    movement: str = Field(default="FCCS_Mvmts_Subtotal", description="Movement member")
    entity: str = Field(default="FCCS_Total Geography")
    period: str = Field(default="Jan")
    years: str = Field(default="FY24")
    scenario: str = Field(default="Actual")
    consolidation: str = Field(default="FCCS_Entity Total")
    session_id: str = Field(default="default")


class BusinessRuleRequest(BaseModel):
    rule_name: str = Field(..., description="Name of the business rule to run")
    parameters: dict = Field(default_factory=dict, description="Rule parameters")
    session_id: str = Field(default="default")


class JournalActionRequest(BaseModel):
    journal_id: str = Field(..., description="Journal ID")
    action: str = Field(..., description="Action: approve, reject, post, unpost, submit, recall")
    session_id: str = Field(default="default")


class DimensionRequest(BaseModel):
    dimension_name: str = Field(..., description="Dimension name (e.g., 'Account', 'Entity')")
    parent_member: Optional[str] = Field(None, description="Parent member to get children of")
    session_id: str = Field(default="default")


# Endpoints

@app.get("/", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "fccs-agent"}


@app.get("/chatgpt-openapi.json", tags=["Health"], include_in_schema=False)
async def chatgpt_openapi():
    """Simplified OpenAPI schema for ChatGPT Actions."""
    return JSONResponse(content={
        "openapi": "3.0.0",
        "info": {
            "title": "FCCS Agent",
            "description": "Oracle FCCS Financial Data API",
            "version": "1.0.0"
        },
        "servers": [{"url": "https://fccs-agent-241840460713.us-central1.run.app"}],
        "paths": {
            "/query": {
                "post": {
                    "operationId": "naturalLanguageQuery",
                    "summary": "Process natural language query about FCCS data",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["query"],
                                    "properties": {
                                        "query": {"type": "string", "description": "Natural language query"}
                                    }
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "Query result"}}
                }
            },
            "/data/smart-retrieve": {
                "post": {
                    "operationId": "smartRetrieve",
                    "summary": "Get financial data from FCCS",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["account"],
                                    "properties": {
                                        "account": {"type": "string", "description": "Account member"},
                                        "entity": {"type": "string", "default": "FCCS_Total Geography"},
                                        "period": {"type": "string", "default": "Jan"},
                                        "years": {"type": "string", "default": "FY24"},
                                        "scenario": {"type": "string", "default": "Actual"}
                                    }
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "Financial data"}}
                }
            },
            "/application": {
                "get": {
                    "operationId": "getApplicationInfo",
                    "summary": "Get FCCS application information",
                    "responses": {"200": {"description": "Application info"}}
                }
            },
            "/dimensions": {
                "get": {
                    "operationId": "getDimensions",
                    "summary": "List all dimensions",
                    "responses": {"200": {"description": "List of dimensions"}}
                }
            },
            "/journals": {
                "get": {
                    "operationId": "getJournals",
                    "summary": "List journals",
                    "parameters": [
                        {"name": "period", "in": "query", "schema": {"type": "string", "default": "Jan"}},
                        {"name": "year", "in": "query", "schema": {"type": "string", "default": "FY24"}}
                    ],
                    "responses": {"200": {"description": "List of journals"}}
                }
            },
            "/rules/run": {
                "post": {
                    "operationId": "runBusinessRule",
                    "summary": "Run a business rule",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["rule_name"],
                                    "properties": {
                                        "rule_name": {"type": "string", "description": "Rule name"}
                                    }
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "Rule result"}}
                }
            },
            "/jobs": {
                "get": {
                    "operationId": "listJobs",
                    "summary": "List recent jobs",
                    "responses": {"200": {"description": "List of jobs"}}
                }
            }
        }
    })


@app.post("/query", response_model=QueryResponse, tags=["Query"])
async def natural_language_query(request: QueryRequest):
    """
    Process a natural language query about FCCS data.

    Examples:
    - "What is the revenue for FY24?"
    - "Show me the consolidation breakdown for Total Assets"
    - "Run the Consolidate business rule"
    """
    try:
        result = await agentic_query(request.query, request.session_id)
        return QueryResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/tools/execute", tags=["Tools"])
async def execute_tool_endpoint(request: ToolRequest):
    """Execute a specific FCCS tool by name."""
    try:
        result = await execute_tool(
            request.tool_name,
            request.arguments,
            request.session_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tools", tags=["Tools"])
async def list_tools():
    """List all available FCCS tools."""
    tools = get_tool_definitions()
    return {
        "tools": [
            {
                "name": t["name"],
                "description": t.get("description", ""),
            }
            for t in tools
        ]
    }


# Data Retrieval Endpoints

@app.post("/data/slice", tags=["Data"])
async def get_data_slice(request: DataSliceRequest):
    """
    Export a data slice from FCCS cube.

    Retrieves financial data for specified dimensions.
    """
    try:
        result = await execute_tool(
            "export_data_slice",
            {
                "accounts": request.accounts,
                "entities": request.entities,
                "periods": request.periods,
                "years": request.years,
                "scenarios": request.scenarios,
                "currencies": request.currencies,
            },
            request.session_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/data/smart-retrieve", tags=["Data"])
async def smart_retrieve(request: SmartRetrieveRequest):
    """
    Smart data retrieval with automatic dimension resolution.

    Simpler interface that handles dimension defaults automatically.
    """
    try:
        result = await execute_tool(
            "smart_retrieve",
            {
                "account": request.account,
                "entity": request.entity,
                "period": request.period,
                "years": request.years,
                "scenario": request.scenario,
                "consolidation": request.consolidation,
            },
            request.session_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/data/consolidation-breakdown", tags=["Data"])
async def consolidation_breakdown(request: ConsolidationBreakdownRequest):
    """
    Get consolidation breakdown showing Entity Input, Adjustments, and Consolidated values.
    """
    try:
        result = await execute_tool(
            "smart_retrieve_consolidation_breakdown",
            {
                "account": request.account,
                "entity": request.entity,
                "period": request.period,
                "years": request.years,
                "scenario": request.scenario,
            },
            request.session_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/data/movement-analysis", tags=["Data"])
async def movement_analysis(request: MovementAnalysisRequest):
    """
    Analyze account movements across different movement dimension members.
    """
    try:
        result = await execute_tool(
            "smart_retrieve_with_movement",
            {
                "account": request.account,
                "movement": request.movement,
                "entity": request.entity,
                "period": request.period,
                "years": request.years,
                "scenario": request.scenario,
                "consolidation": request.consolidation,
            },
            request.session_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Business Rules & Jobs

@app.post("/rules/run", tags=["Rules"])
async def run_business_rule(request: BusinessRuleRequest):
    """
    Run a business rule in FCCS.

    Common rules: Consolidate, Force Consolidate, Translate, Force Translate
    """
    try:
        result = await execute_tool(
            "run_business_rule",
            {
                "rule_name": request.rule_name,
                "parameters": request.parameters,
            },
            request.session_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/jobs", tags=["Jobs"])
async def list_jobs(limit: int = 10, session_id: str = "default"):
    """List recent jobs."""
    try:
        result = await execute_tool("list_jobs", {"limit": limit}, session_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/jobs/{job_id}", tags=["Jobs"])
async def get_job_status(job_id: str, session_id: str = "default"):
    """Get status of a specific job."""
    try:
        result = await execute_tool("get_job_status", {"job_id": job_id}, session_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Journals

@app.get("/journals", tags=["Journals"])
async def get_journals(
    period: str = "Jan",
    year: str = "FY24",
    status: Optional[str] = None,
    session_id: str = "default"
):
    """List journals for a period."""
    try:
        args = {"period": period, "year": year}
        if status:
            args["status"] = status
        result = await execute_tool("get_journals", args, session_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/journals/{journal_id}", tags=["Journals"])
async def get_journal_details(journal_id: str, session_id: str = "default"):
    """Get details of a specific journal."""
    try:
        result = await execute_tool(
            "get_journal_details",
            {"journal_id": journal_id},
            session_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/journals/action", tags=["Journals"])
async def perform_journal_action(request: JournalActionRequest):
    """
    Perform an action on a journal.

    Actions: approve, reject, post, unpost, submit, recall
    """
    try:
        result = await execute_tool(
            "perform_journal_action",
            {
                "journal_id": request.journal_id,
                "action": request.action,
            },
            request.session_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Dimensions

@app.get("/dimensions", tags=["Dimensions"])
async def get_dimensions(session_id: str = "default"):
    """List all dimensions in the application."""
    try:
        result = await execute_tool("get_dimensions", {}, session_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/dimensions/members", tags=["Dimensions"])
async def get_dimension_members(request: DimensionRequest):
    """Get members of a dimension, optionally under a parent."""
    try:
        args = {"dimension_name": request.dimension_name}
        if request.parent_member:
            args["parent_member"] = request.parent_member
        result = await execute_tool("get_members", args, request.session_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/dimensions/{dimension_name}/hierarchy", tags=["Dimensions"])
async def get_dimension_hierarchy(
    dimension_name: str,
    session_id: str = "default"
):
    """Get the full hierarchy of a dimension."""
    try:
        result = await execute_tool(
            "get_dimension_hierarchy",
            {"dimension_name": dimension_name},
            session_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Application Info

@app.get("/application", tags=["Application"])
async def get_application_info(session_id: str = "default"):
    """Get FCCS application information."""
    try:
        result = await execute_tool("get_application_info", {}, session_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def create_app() -> FastAPI:
    """Create and return the FastAPI app."""
    return app


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
