"""ADK Agent - Main agent definition with all FCCS tools."""

import sys
from typing import Any, Optional

from fccs_agent.config import config, FCCSConfig
from fccs_agent.client.fccs_client import FccsClient
from fccs_agent.services.feedback_service import (
    init_feedback_service,
    before_tool_callback,
    after_tool_callback,
    get_feedback_service
)
from fccs_agent.services.cache_service import (
    init_cache_service,
    get_cache_service
)
from fccs_agent.services.semantic_search import init_semantic_search
from fccs_agent.services.valid_intersections import init_valid_intersections
from fccs_agent.services.personalization_service import (
    init_personalization_service,
    get_personalization_service
)
from fccs_agent.services.rl_service import (
    init_rl_service,
    get_rl_service
)
from fccs_agent.intelligence.orchestrator import FCCSOrchestrator

# Import all tool modules
from fccs_agent.tools import application, jobs, dimensions, journals, data, reports, consolidation, memo, feedback, local_data, exploration, consolidation_ops, intercompany, personalization

# Global state
_fccs_client: Optional[FccsClient] = None
_app_name: Optional[str] = None
_session_state: dict[str, dict[str, Any]] = {}  # Track session state for RL
_orchestrator: Optional[FCCSOrchestrator] = None
_pipeline = None

# Agent instruction for ADK
AGENT_INSTRUCTION = """You are an expert assistant for Oracle EPM Cloud Financial Consolidation and Close (FCCS).

You help users with:
- Querying financial data from FCCS cubes
- Running consolidation and business rules
- Managing journals (create, approve, post)
- Generating financial reports and memos
- Managing dimensions and metadata

Respond in the same language as the user (English or Portuguese).
Always provide clear explanations of what you're doing and the results.

Available tools:
- get_application_info: Get FCCS application details
- list_jobs, get_job_status: Monitor jobs
- run_business_rule, run_data_rule: Execute rules
- get_dimensions, get_members, get_dimension_hierarchy: Explore dimensions
- get_journals, get_journal_details, perform_journal_action: Journal management
- export_data_slice, smart_retrieve, smart_retrieve_consolidation_breakdown, smart_retrieve_with_movement: Query financial data
- import_data_slice, smart_import, smart_import_batch: Write/import financial data
- run_consolidation, run_translation, run_force_consolidation: Execute consolidation operations
- get_ownership_structure, calculate_minority_interest: Ownership management
- get_period_close_status, lock_period, unlock_period: Period close workflow
- get_icp_balances, get_icp_mismatches, get_icp_elimination_summary: Intercompany analysis
- create_icp_elimination_journal: Create ICP elimination entries
- generate_report, get_report_job_status: Generate reports
- submit_feedback, get_recent_executions: Provide feedback to improve RL learning
- explore_dimension, search_members, get_drill_suggestions: OLAP-aware dimension navigation with semantic search
- get_personalization_status, update_personalization_item, set_personalization_preference, get_personalization_preferences: Onboarding checklist and preferences
- And more consolidation and data management tools

After executing a tool, you can use submit_feedback with the execution_id from the result
to rate the execution (1-5 stars) and help the system learn.
"""


def get_client() -> FccsClient:
    """Get the FCCS client instance."""
    global _fccs_client
    if _fccs_client is None:
        _fccs_client = FccsClient(config)
    return _fccs_client


def get_app_name() -> Optional[str]:
    """Get the current application name."""
    return _app_name


async def initialize_agent(cfg: Optional[FCCSConfig] = None) -> str:
    """Initialize the agent and connect to FCCS.

    Returns:
        str: The application name or error message.
    """
    global _fccs_client, _app_name

    use_config = cfg or config

    # Initialize FCCS client
    _fccs_client = FccsClient(use_config)

    # Set client reference in all tool modules
    application.set_client(_fccs_client)
    jobs.set_client(_fccs_client)
    dimensions.set_client(_fccs_client)
    journals.set_client(_fccs_client)
    data.set_client(_fccs_client)
    reports.set_client(_fccs_client)
    consolidation.set_client(_fccs_client)
    memo.set_client(_fccs_client)
    consolidation_ops.set_client(_fccs_client)
    intercompany.set_client(_fccs_client)

    # Initialize feedback service (optional - don't break if it fails)
    feedback_service = None
    try:
        feedback_service = init_feedback_service(use_config.database_url)
        print("Feedback service initialized", file=sys.stderr)
    except Exception as e:
        print(f"Warning: Could not initialize feedback service: {e}", file=sys.stderr)
        print("Tool execution will continue without feedback tracking", file=sys.stderr)
        # Set feedback service to None so callbacks know it's not available
        from fccs_agent.services.feedback_service import _feedback_service
        import fccs_agent.services.feedback_service as feedback_module
        feedback_module._feedback_service = None

    # Initialize cache service
    try:
        init_cache_service(use_config.database_url)
        print("Cache service initialized", file=sys.stderr)
    except Exception as e:
        print(f"Warning: Could not initialize cache service: {e}", file=sys.stderr)

    # Initialize semantic search service
    try:
        semantic_service = init_semantic_search(use_config.database_url)
        if semantic_service and not semantic_service.get_indexed_dimensions():
            from fccs_agent.services.semantic_search import index_from_csvs
            indexed = index_from_csvs(semantic_service)
            total_indexed = sum(indexed.values())
            print(f"Semantic search indexed {total_indexed} members", file=sys.stderr)
        print("Semantic search service initialized", file=sys.stderr)
    except Exception as e:
        print(f"Warning: Could not initialize semantic search: {e}", file=sys.stderr)

    # Initialize valid intersections cache
    try:
        init_valid_intersections(use_config.database_url)
        print("Valid intersections cache initialized", file=sys.stderr)
    except Exception as e:
        print(f"Warning: Could not initialize valid intersections cache: {e}", file=sys.stderr)

    # Initialize personalization tracker
    try:
        init_personalization_service(use_config.database_url)
        print("Personalization service initialized", file=sys.stderr)
    except Exception as e:
        print(f"Warning: Could not initialize personalization service: {e}", file=sys.stderr)

    # Initialize RL service (optional - only if feedback service is available and RL enabled)
    if use_config.rl_enabled and feedback_service:
        try:
            init_rl_service(
                feedback_service,
                use_config.database_url,
                exploration_rate=use_config.rl_exploration_rate,
                learning_rate=use_config.rl_learning_rate,
                discount_factor=use_config.rl_discount_factor,
                min_samples=use_config.rl_min_samples
            )
            print("RL service initialized", file=sys.stderr)
        except Exception as e:
            print(f"Warning: Could not initialize RL service: {e}", file=sys.stderr)
            print("RL features will be disabled", file=sys.stderr)

    # Try to connect to FCCS and get application name
    try:
        print("Connecting to FCCS to retrieve application info...", file=sys.stderr)
        apps = await _fccs_client.get_applications()
        if apps and apps.get("items") and len(apps["items"]) > 0:
            _app_name = apps["items"][0]["name"]
            print(f"Connected to FCCS Application: {_app_name}", file=sys.stderr)

            # Set app name in tool modules that need it
            jobs.set_app_name(_app_name)
            dimensions.set_app_name(_app_name)
            journals.set_app_name(_app_name)
            data.set_app_name(_app_name)
            consolidation.set_app_name(_app_name)
            memo.set_app_name(_app_name)
            consolidation_ops.set_app_name(_app_name)
            intercompany.set_app_name(_app_name)

            try:
                personalization_service = get_personalization_service()
                if personalization_service:
                    personalization_service.ensure_checklist(session_id="default")
                    personalization_service.set_preference("default", "app_name", _app_name)
                    personalization_service.update_item("default", "app_name", status="done", value=_app_name)
            except Exception:
                pass

            return _app_name
        else:
            print("No applications found", file=sys.stderr)
            return "No applications found"
    except Exception as e:
        print(f"Initialization warning: Could not connect to FCCS: {e}", file=sys.stderr)
        return f"Connection failed: {e}"


async def close_agent():
    """Clean up agent resources."""
    global _fccs_client
    if _fccs_client:
        await _fccs_client.close()
        _fccs_client = None


AGENTIC_TOOL_DEFINITION = {
    "name": "agentic_query",
    "description": "Process a natural language FCCS query through the agentic reasoning pipeline.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "User query in natural language."},
            "session_id": {"type": "string", "description": "Optional session id for context.", "default": "default"},
        },
        "required": ["query"],
    },
}


def get_orchestrator() -> FCCSOrchestrator:
    """Get or create the agentic orchestrator."""
    global _orchestrator
    if _orchestrator is None:
        orchestrator = FCCSOrchestrator(
            db_url=config.database_url,
            anthropic_api_key=config.anthropic_api_key
        )
        handlers = {
            name: handler
            for name, handler in TOOL_HANDLERS.items()
            if name != "agentic_query"
        }
        orchestrator.set_tool_handlers(handlers)
        rl_service = get_rl_service()
        if rl_service:
            orchestrator.set_rl_service(rl_service)
        _orchestrator = orchestrator
    return _orchestrator


async def agentic_query(query: str, session_id: str = "default") -> dict[str, Any]:
    """Run the full agentic reasoning pipeline for a natural language query using the orchestrator."""
    orchestrator = get_orchestrator()
    response = await orchestrator.process(query, session_id=session_id)
    
    data = {
        "intent": {
            "name": response.intent.name if response.intent else "unknown",
            "confidence": response.intent.confidence if response.intent else 0.0,
        },
        "plan": {
            "name": response.plan.name if response.plan else "None",
            "description": response.plan.description if response.plan else "None",
            "steps": [
                {
                    "tool": step.tool_name,
                    "parameters": step.parameters,
                    "description": step.description,
                    "status": step.status.value
                }
                for step in response.plan.steps
            ] if response.plan else [],
        },
        "results": response.results,
        "synthesis": response.synthesis,
        "recommendations": response.recommendations,
        "error_explanation": response.error_explanation,
    }
    
    return {
        "status": "success" if response.success else "error",
        "data": data,
        "error": response.error_explanation if not response.success else None,
    }


# Tool registry - maps tool names to handler functions
TOOL_HANDLERS = {
    # Application
    "get_application_info": application.get_application_info,
    "get_rest_api_version": application.get_rest_api_version,
    # Jobs
    "list_jobs": jobs.list_jobs,
    "get_job_status": jobs.get_job_status,
    "run_business_rule": jobs.run_business_rule,
    "run_data_rule": jobs.run_data_rule,
    # Dimensions
    "get_dimensions": dimensions.get_dimensions,
    "get_members": dimensions.get_members,
    "get_dimension_hierarchy": dimensions.get_dimension_hierarchy,
    # Journals
    "get_journals": journals.get_journals,
    "get_journal_details": journals.get_journal_details,
    "perform_journal_action": journals.perform_journal_action,
    "update_journal_period": journals.update_journal_period,
    "export_journals": journals.export_journals,
    "import_journals": journals.import_journals,
    # Data
    "export_data_slice": data.export_data_slice,
    "smart_retrieve": data.smart_retrieve,
    "smart_retrieve_consolidation_breakdown": data.smart_retrieve_consolidation_breakdown,
    "smart_retrieve_with_movement": data.smart_retrieve_with_movement,
    "copy_data": data.copy_data,
    "clear_data": data.clear_data,
    "import_data_slice": data.import_data_slice,
    "smart_import": data.smart_import,
    "smart_import_batch": data.smart_import_batch,
    # Reports
    "generate_report": reports.generate_report,
    "get_report_job_status": reports.get_report_job_status,
    "generate_report_script": reports.generate_report_script,
    # Consolidation
    "export_consolidation_rulesets": consolidation.export_consolidation_rulesets,
    "import_consolidation_rulesets": consolidation.import_consolidation_rulesets,
    "validate_metadata": consolidation.validate_metadata,
    "generate_intercompany_matching_report": consolidation.generate_intercompany_matching_report,
    "import_supplementation_data": consolidation.import_supplementation_data,
    "deploy_form_template": consolidation.deploy_form_template,
    "generate_consolidation_process_report": consolidation.generate_consolidation_process_report,
    # Memo
    "generate_system_pitch": memo.generate_system_pitch,
    "generate_investment_memo": memo.generate_investment_memo,
    # Feedback
    "submit_feedback": feedback.submit_feedback,
    "get_recent_executions": feedback.get_recent_executions,
    "rate_last_tool": feedback.rate_last_tool,
    # Local Data
    "query_local_metadata": local_data.query_local_metadata,
    # Exploration (OLAP-aware)
    "explore_dimension": exploration.explore_dimension,
    "search_members": exploration.search_members,
    "get_drill_suggestions": exploration.get_drill_suggestions,
    "list_available_dimensions": exploration.list_available_dimensions,
    # Consolidation Operations (new)
    "run_consolidation": consolidation_ops.run_consolidation,
    "run_translation": consolidation_ops.run_translation,
    "run_force_consolidation": consolidation_ops.run_force_consolidation,
    "get_ownership_structure": consolidation_ops.get_ownership_structure,
    "calculate_minority_interest": consolidation_ops.calculate_minority_interest,
    "get_period_close_status": consolidation_ops.get_period_close_status,
    "lock_period": consolidation_ops.lock_period,
    "unlock_period": consolidation_ops.unlock_period,
    # Intercompany (new)
    "get_icp_balances": intercompany.get_icp_balances,
    "get_icp_mismatches": intercompany.get_icp_mismatches,
    "create_icp_elimination_journal": intercompany.create_icp_elimination_journal,
    "get_icp_elimination_summary": intercompany.get_icp_elimination_summary,
    # Personalization
    "get_personalization_status": personalization.get_personalization_status,
    "update_personalization_item": personalization.update_personalization_item,
    "set_personalization_preference": personalization.set_personalization_preference,
    "get_personalization_preferences": personalization.get_personalization_preferences,
    # Agentic
    "agentic_query": agentic_query,
}

# Collect all tool definitions
ALL_TOOL_DEFINITIONS = (
    application.TOOL_DEFINITIONS +
    jobs.TOOL_DEFINITIONS +
    dimensions.TOOL_DEFINITIONS +
    journals.TOOL_DEFINITIONS +
    data.TOOL_DEFINITIONS +
    reports.TOOL_DEFINITIONS +
    consolidation.TOOL_DEFINITIONS +
    memo.TOOL_DEFINITIONS +
    feedback.TOOL_DEFINITIONS +
    local_data.TOOL_DEFINITIONS +
    exploration.TOOL_DEFINITIONS +
    consolidation_ops.TOOL_DEFINITIONS +
    intercompany.TOOL_DEFINITIONS +
    personalization.TOOL_DEFINITIONS +
    [AGENTIC_TOOL_DEFINITION]
)


async def execute_tool(
    tool_name: str,
    arguments: dict[str, Any],
    session_id: str = "default",
    user_query: str = "",
    use_rl: bool = True,
    confirmed: bool = False
) -> dict[str, Any]:
    """Execute a tool by name with given arguments.

    Args:
        tool_name: Name of the tool to execute.
        arguments: Arguments to pass to the tool.
        session_id: Session ID for feedback tracking.
        user_query: Optional user query for RL context.
        use_rl: Whether to use RL for learning (default: True).
        confirmed: Whether the user has confirmed destructive operations.

    Returns:
        dict: Tool execution result with optional RL metadata.
    """
    handler = TOOL_HANDLERS.get(tool_name)
    if not handler:
        return {"status": "error", "error": f"Unknown tool: {tool_name}"}

    # Initialize session state if needed
    if session_id not in _session_state:
        _session_state[session_id] = {
            "tool_sequence": [],
            "previous_tool": None,
            "session_length": 0,
            "user_query": user_query
        }

    session_state = _session_state[session_id]
    previous_tool = session_state["previous_tool"]
    session_length = session_state["session_length"]

    # Track execution start (non-blocking)
    try:
        before_tool_callback(session_id, tool_name, arguments)
    except Exception:
        pass  # Ignore feedback service errors

    # Get RL service for context and learning
    rl_service = get_rl_service() if use_rl else None
    context_hash = None
    
    if rl_service:
        try:
            # Create context hash for RL
            context_hash = rl_service.tool_selector.create_context_hash(
                user_query or session_state.get("user_query", ""),
                previous_tool,
                session_length
            )
        except Exception:
            pass  # Continue without RL context

    try:
        result = await handler(**arguments)

        # Update session state FIRST (needed for next context hash calculation)
        session_state["tool_sequence"].append(tool_name)
        session_state["previous_tool"] = tool_name
        session_state["session_length"] += 1

        # Track execution end (non-blocking)
        # This will also trigger RL policy update via feedback_service callback
        execution_id = None
        try:
            execution_id = after_tool_callback(session_id, tool_name, arguments, result)
            
            # Include execution_id in result for easy feedback submission
            if execution_id and execution_id > 0:
                result["execution_id"] = execution_id

            # Update RL policy with context if available
            if rl_service and context_hash and execution_id:
                try:
                    # Calculate next context hash (state after action)
                    next_context_hash = rl_service.tool_selector.create_context_hash(
                        user_query or session_state.get("user_query", ""),
                        session_state["previous_tool"],  # Now updated to current tool
                        session_state["session_length"]   # Now incremented
                    )

                    # Get execution from feedback service to calculate reward
                    feedback_service = get_feedback_service()
                    if feedback_service:
                        from sqlalchemy.orm import sessionmaker
                        from sqlalchemy import create_engine
                        from fccs_agent.services.feedback_service import ToolExecution

                        engine = create_engine(config.database_url)
                        Session = sessionmaker(bind=engine)
                        with Session() as session:
                            execution = session.query(ToolExecution).get(execution_id)
                            if execution:
                                reward = rl_service.calculate_reward(execution)
                                # Full Q-learning update with next state
                                rl_service.update_policy(
                                    session_id,
                                    tool_name,
                                    context_hash,
                                    reward,
                                    next_context_hash=next_context_hash,
                                    available_tools=list(TOOL_HANDLERS.keys())
                                )
                except Exception:
                    pass  # Silently fail RL updates
        except Exception:
            pass  # Ignore feedback service errors

        # Add RL metadata to result if available
        if rl_service and context_hash:
            try:
                confidence = rl_service.get_tool_confidence(tool_name, context_hash)
                result["rl_metadata"] = {
                    "confidence": confidence,
                    "context_hash": context_hash
                }
            except Exception:
                pass

        return result
    except Exception as e:
        error_result = {"status": "error", "error": str(e)}
        try:
            after_tool_callback(session_id, tool_name, arguments, error_result)
        except Exception:
            pass  # Ignore feedback service errors
        
        # Update session state even on error
        session_state["tool_sequence"].append(tool_name)
        session_state["previous_tool"] = tool_name
        session_state["session_length"] += 1
        
        return error_result


async def execute_tool_with_rl(
    tool_name: str,
    arguments: dict[str, Any],
    session_id: str = "default",
    user_query: str = ""
) -> dict[str, Any]:
    """Execute tool with RL-enhanced recommendations.
    
    This is a convenience wrapper that:
    1. Gets RL recommendations before execution
    2. Executes the tool
    3. Updates RL policy after execution
    
    Args:
        tool_name: Name of the tool to execute.
        arguments: Arguments to pass to the tool.
        session_id: Session ID for feedback tracking.
        user_query: User query for RL context.
        
    Returns:
        dict: Tool execution result with RL recommendations.
    """
    rl_service = get_rl_service()
    recommendations = None
    
    if rl_service:
        try:
            session_state = _session_state.get(session_id, {})
            recommendations = rl_service.get_tool_recommendations(
                user_query=user_query or session_state.get("user_query", ""),
                previous_tool=session_state.get("previous_tool"),
                session_length=session_state.get("session_length", 0),
                available_tools=list(TOOL_HANDLERS.keys())
            )
        except Exception:
            pass  # Continue without recommendations
    
    # Execute tool
    result = await execute_tool(tool_name, arguments, session_id, user_query, use_rl=True)
    
    # Add recommendations to result if available
    if recommendations:
        result["rl_recommendations"] = recommendations[:5]  # Top 5 recommendations
    
    return result


def get_pipeline():
    """Get or create the re-architected agentic pipeline."""
    global _pipeline
    if _pipeline is None:
        from fccs_agent.pipeline.anthropic_adapter import load_anthropic_adapter
        from fccs_agent.pipeline.anthropic_planner import AnthropicPlanner
        from fccs_agent.pipeline.engine import AgenticPipeline
        from fccs_agent.pipeline.heuristic_planner import HeuristicPlanner
        from fccs_agent.pipeline.registry import ToolRegistry

        adapter = load_anthropic_adapter(config.model_id, config.anthropic_api_key)
        if adapter:
            planner = AnthropicPlanner(adapter)
        else:
            planner = HeuristicPlanner()

        registry = ToolRegistry(ALL_TOOL_DEFINITIONS, execute_tool)
        _pipeline = AgenticPipeline(planner, registry)
    return _pipeline


def finalize_session(session_id: str, outcome: str = "success"):
    """Finalize a session and log episode for RL learning.
    
    Args:
        session_id: Session ID to finalize.
        outcome: Session outcome ('success', 'partial', 'failure').
    """
    if session_id not in _session_state:
        return
    
    session_state = _session_state[session_id]
    tool_sequence = session_state.get("tool_sequence", [])
    
    if not tool_sequence:
        return
    
    rl_service = get_rl_service()
    if rl_service:
        try:
            # Calculate episode reward (sum of individual rewards would be ideal,
            # but for simplicity, use a heuristic based on outcome)
            episode_reward = 10.0 if outcome == "success" else (5.0 if outcome == "partial" else -5.0)
            
            rl_service.log_episode(
                session_id,
                tool_sequence,
                episode_reward,
                outcome
            )
        except Exception:
            pass  # Silently fail
    
    # Clean up session state (keep for a while in case of late feedback)
    # Could implement TTL cleanup later


def get_tool_definitions() -> list[dict]:
    """Get all tool definitions for MCP server."""
    return ALL_TOOL_DEFINITIONS
