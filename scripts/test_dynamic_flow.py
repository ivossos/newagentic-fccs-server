import asyncio
import sys
from pathlib import Path

# Add workspace root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fccs_agent.intelligence.orchestrator import FCCSOrchestrator, OrchestratorConfig
from fccs_agent.intelligence.context_memory import ContextMemory

async def test_dynamic_flow():
    # Setup orchestrator with mock handlers
    # Use a local sqlite for testing context
    db_url = "sqlite:///data/test_context.db"
    orchestrator = FCCSOrchestrator(db_url=db_url)
    
    # Mock handlers
    async def mock_query_local_metadata(**kwargs):
        print(f"[Mock] query_local_metadata called with: {kwargs}")
        # Return matched members for both dimensions if requested
        results = []
        if kwargs.get("dimension") == "Account":
            results.append({
                "dimension": "Account",
                "member": "FCCS_Net Income Real",
                "properties": {}
            })
        elif kwargs.get("dimension") == "Entity":
            results.append({
                "dimension": "Entity",
                "member": "E501_Actual",
                "properties": {}
            })
        return {
            "status": "success",
            "data": results
        }
        
    async def mock_smart_retrieve(**kwargs):
        print(f"[Mock] smart_retrieve called with: {kwargs}")
        return {
            "status": "success",
            "data": {"value": 1000}
        }
        
    orchestrator.set_tool_handlers({
        "query_local_metadata": mock_query_local_metadata,
        "smart_retrieve": mock_smart_retrieve
    })
    
    # We need to mock the execute_tool in agent.py because orchestrator calls it
    # For this test, let's just patch the orchestrator's _execute_step to call handlers directly
    # instead of importing from agent.py (which would try to initialize the whole agent)
    
    original_execute_step = orchestrator._execute_step
    
    async def patched_execute_step(step, session_id, user_query):
        tool_name = step.tool_name
        # Re-resolve parameters like in the real orchestrator
        params = step.parameters.copy()
        if orchestrator.context_memory:
            suggested = orchestrator.context_memory.get_suggested_params(session_id, tool_name)
            defaults = {"entity": "FCCS_Total Geography", "consolidation": "FCCS_Entity Total"}
            
            for k, v in suggested.items():
                is_placeholder = k in params and str(params[k]).startswith("%")
                is_missing = k not in params or not params[k]
                is_default = k in defaults and v == defaults[k]
                
                if is_missing or is_placeholder or (k in ["account", "entity"] and not is_default):
                    params[k] = v
        
        handler = orchestrator._tool_handlers.get(tool_name)
        result = await handler(**params)
        
        # Update context
        if result.get("status") == "success":
            orchestrator.context_memory.update_from_result(session_id, tool_name, result)
            
        return {"tool_name": tool_name, "parameters": params, **result}

    orchestrator._execute_step = patched_execute_step
    
    # Test query
    query = "What is the net income for E501?"
    print(f"Processing query: {query}")
    
    # Manually trigger the process (avoiding full agent initialization)
    intent = await orchestrator._classify_intent(query, "test_session")
    plan = orchestrator.planner.create_plan(
        intent=intent.name,
        entities=intent.entities,
        available_tools=orchestrator._available_tools,
        user_query=query
    )
    
    print(f"Plan created: {plan.name}")
    for i, step in enumerate(plan.steps):
        print(f"  Step {i+1}: {step.tool_name} (initial params: {step.parameters})")
        
    results = await orchestrator._execute_plan(plan, "test_session", query)
    
    print("\nExecution Results:")
    for r in results:
        print(f"  Tool: {r['tool_name']}")
        print(f"  Final Params: {r['parameters']}")
        
    # Check if smart_retrieve got "FCCS_Net Income Real"
    smart_retrieve_res = next(r for r in results if r['tool_name'] == 'smart_retrieve')
    if smart_retrieve_res['parameters'].get('account') == "FCCS_Net Income Real":
        print("\nSUCCESS: smart_retrieve used the member found by query_local_metadata!")
    else:
        print("\nFAILURE: smart_retrieve did NOT use the updated member.")

if __name__ == "__main__":
    asyncio.run(test_dynamic_flow())

