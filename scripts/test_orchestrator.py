import asyncio
import sys
from pathlib import Path

# Add workspace root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fccs_agent.config import load_config
from fccs_agent.agent import initialize_agent, close_agent, get_orchestrator

async def test_orchestrator():
    config = load_config()
    print("Initializing agent...")
    await initialize_agent(config)
    
    orchestrator = get_orchestrator()
    query = "Analyze the net loss of -$4.9M in the Income Statement for FY25 Feb YTD Actuals. Provide a breakdown by Entity and Movement."
    
    print(f"Processing query with orchestrator: {query}")
    try:
        response = await orchestrator.process(query)
        print("\nOrchestrator Response:")
        print(f"Success: {response.success}")
        if response.synthesis:
            print(f"Synthesis: {response.synthesis}")
        else:
            print("Results:", response.results)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await close_agent()

if __name__ == "__main__":
    asyncio.run(test_orchestrator())

