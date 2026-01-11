
import asyncio
import os
import sys
from fccs_agent.intelligence.orchestrator import FCCSOrchestrator
from fccs_agent.config import config

async def test():
    print(f"Initializing agent...")
    from fccs_agent.agent import initialize_agent, TOOL_HANDLERS
    await initialize_agent()
    
    print(f"Testing orchestrator with query: What is the Net Income for Entity E501 in Jan FY25?")
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
    
    try:
        # Pre-extract entities to see what's happening
        from fccs_agent.intelligence.intent_classifier import FCCSIntentClassifier
        classifier = FCCSIntentClassifier()
        entities = classifier.extract_entities("What is the Net Income for Entity E501 in Jan FY25?")
        print("Extracted entities:", entities)
        
        response = await orchestrator.process("What is the Net Income for Entity E501 in Jan FY25?")
        print("Success:", response.success)
        print("Intent:", response.intent.name if response.intent else "None")
        print("Error explanation:", response.error_explanation)
        print("Results:")
        for r in response.results:
            print(f"  Tool: {r.get('tool_name')}, Status: {r.get('status')}")
            if r.get('status') == 'error':
                print(f"    Error: {r.get('error')}")
        if response.synthesis:
            print("Synthesis:", response.synthesis)
    except Exception as e:
        import traceback
        traceback.print_exc()
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())

