import asyncio
import sys
from pathlib import Path

# Add workspace root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fccs_agent.config import load_config
from fccs_agent.agent import initialize_agent, close_agent, get_orchestrator

async def analyze():
    config = load_config()
    print("Initializing agent...")
    await initialize_agent(config)
    
    orchestrator = get_orchestrator()
    # Explicit query for breakdown by Entity and Movement
    query = "Analyze net loss of -$4.9M in Income Statement for FY25 Feb YTD Actuals. Breakdown by Consolidation and Movement."
    
    print(f"Processing: {query}")
    try:
        response = await orchestrator.process(query)
        print("\n--- ANALYSIS RESULTS ---")
        if response.results:
            for res in response.results:
                tool = res.get("tool_name")
                status = res.get("status")
                print(f"\nTool: {tool} [{status}]")
                if status == "success":
                    data = res.get("data")
                    if tool == "smart_retrieve":
                        print(f"POV: {data.get('pov')}")
                        print(f"Value: {data.get('rows')[0]['data'][0] if data.get('rows') else 'N/A'}")
                    elif tool == "smart_retrieve_consolidation_breakdown":
                        print(f"Consolidation Breakdown: {data.get('consolidation_breakdown')}")
                    elif tool == "smart_retrieve_with_movement":
                        print(f"Movement: {data.get('movement')}")
                        print(f"Value: {data.get('rows')[0]['data'][0] if data.get('rows') else 'N/A'}")
                else:
                    print(f"Error: {res.get('error')}")
        
        if response.synthesis:
            print(f"\nSynthesis: {response.synthesis}")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await close_agent()

if __name__ == "__main__":
    asyncio.run(analyze())

