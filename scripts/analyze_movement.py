import asyncio
import sys
from pathlib import Path

# Add workspace root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fccs_agent.config import load_config
from fccs_agent.agent import initialize_agent, close_agent, get_orchestrator
from fccs_agent.tools.data import smart_retrieve_with_movement

async def analyze():
    config = load_config()
    await initialize_agent(config)
    
    print("\n--- MOVEMENT BREAKDOWN ---")
    # Retrieve breakdown by major movement members
    movements = ["FCCS_Mvmts_NetIncome", "FCCS_Mvmts_Total", "FCCS_Mvmts_Subtotal"]
    
    for mvm in movements:
        try:
            result = await smart_retrieve_with_movement(
                account="FCCS_Income Statement",
                entity="FCCS_Total Geography",
                period="Feb",
                years="FY25",
                scenario="Actual",
                movement=mvm
            )
            if result.get("status") == "success":
                val = result["data"]["rows"][0]["data"][0] if result["data"].get("rows") else "0.0"
                print(f"Movement: {mvm} -> Value: {val}")
        except Exception as e:
            print(f"Error for {mvm}: {e}")

    await close_agent()

if __name__ == "__main__":
    asyncio.run(analyze())

