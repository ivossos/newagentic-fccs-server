
import asyncio
import sys
from fccs_agent.agent import initialize_agent, get_orchestrator, close_agent

async def debug_agentic_query(query):
    print(f"Step 1: Initializing agent...")
    await initialize_agent()
    
    print(f"Step 2: Getting orchestrator...")
    orchestrator = get_orchestrator()
    
    print(f"Step 3: Processing query: {query}")
    try:
        # We manually call the steps of orchestrator.process to see where it fails
        print("Substep 3.1: Intent classification...")
        intent = await orchestrator._classify_intent(query, "default")
        print(f"Intent classified: {intent.name}")
        
        print("Substep 3.2: Enrichment...")
        context_params = {}
        if orchestrator.context_memory:
            orchestrator.context_memory.update_from_entities("default", intent.entities)
            context_params = orchestrator.context_memory.get_suggested_params(
                "default",
                intent.suggested_tools[0] if intent.suggested_tools else ""
            )
        enriched_entities = {**context_params, **intent.entities}
        
        print("Substep 3.3: Planning...")
        plan = orchestrator.planner.create_plan(
            intent=intent.name,
            entities=enriched_entities,
            available_tools=orchestrator._available_tools,
            sub_intent=intent.sub_intent,
            suggested_tools=intent.suggested_tools,
            user_query=query
        )
        print(f"Plan created: {plan.name} with {len(plan.steps)} steps")
        
        print("Substep 3.4: Execution...")
        results = await orchestrator._execute_plan(plan, "default", query)
        print(f"Execution finished with {len(results)} results")
        
        return results
    except Exception as e:
        print(f"ERROR in orchestrator.process: {e}")
        import traceback
        traceback.print_exc()
        raise e
    finally:
        await close_agent()

if __name__ == "__main__":
    query = "get app info"
    asyncio.run(debug_agentic_query(query))

