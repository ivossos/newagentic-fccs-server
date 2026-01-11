import asyncio
import sys
from pathlib import Path

# Add workspace root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fccs_agent.config import load_config
from fccs_agent.agent import initialize_agent, close_agent
from fccs_agent.tools.data import smart_retrieve
from fccs_agent.tools.dimensions import get_members

async def get_underperformers():
    config = load_config()
    await initialize_agent(config)
    
    print("Fetching level 1 entities from CSV...")
    entities = []
    import csv
    csv_path = Path("data/Ravi_ExportedMetadata_Entity.csv")
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get(" Parent") == "FCCS_Total Geography":
                entities.append(row.get("Entity"))
    
    if not entities:
        entities = ["Industrial Segment", "Energy Segment", "Fire Protection Segment", "Administrative Segment"]
    
    results = []
    
    print(f"Analyzing {len(entities)} entities for Dec FY24...")
    
    for ent in entities:
        print(f"Processing {ent}...")
        try:
            res = await smart_retrieve(
                account="FCCS_Net Income",
                entity=ent,
                period="Dec",
                years="FY24",
                scenario="Actual"
            )
            if res.get("status") == "success":
                val = float(res["data"]["rows"][0]["data"][0]) if res["data"].get("rows") else 0.0
                results.append({"entity": ent, "net_income": val})
            else:
                print(f"Warning: Failed to retrieve data for {ent}: {res.get('error')}")
        except Exception as e:
            print(f"Error for {ent}: {e}")

    # Sort by net income ascending (underperformers first)
    results.sort(key=lambda x: x["net_income"])
    
    print("\n--- TOP 10 UNDERPERFORMERS 2024 (Level 1) ---")
    for i, res in enumerate(results[:10], 1):
        print(f"{i}. {res['entity']}: ${res['net_income']:,.2f}")

    await close_agent()

if __name__ == "__main__":
    asyncio.run(get_underperformers())

