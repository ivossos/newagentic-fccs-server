import asyncio
import sys
from pathlib import Path

# Add workspace root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fccs_agent.config import load_config
from fccs_agent.agent import initialize_agent, close_agent
from fccs_agent.tools.data import smart_retrieve

async def analyze():
    config = load_config()
    await initialize_agent(config)
    
    print("\n--- ENTITY BREAKDOWN ---")
    entities = ["Industrial Segment", "Energy Segment", "Fire Protection Segment", "Administrative Segment"]
    
    for ent in entities:
        try:
            result = await smart_retrieve(
                account="FCCS_Income Statement",
                entity=ent,
                period="Feb",
                years="FY25",
                scenario="Actual"
            )
            if result.get("status") == "success":
                val = result["data"]["rows"][0]["data"][0] if result["data"].get("rows") else "0.0"
                print(f"Entity: {ent} -> Value: {val}")
        except Exception as e:
            print(f"Error for {ent}: {e}")

    await close_agent()

if __name__ == "__main__":
    asyncio.run(analyze())

