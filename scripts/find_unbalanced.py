import asyncio
import sys
from pathlib import Path

# Add workspace root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fccs_agent.config import load_config
from fccs_agent.agent import initialize_agent, close_agent
from fccs_agent.tools.data import smart_retrieve

async def check_unbalanced():
    config = load_config()
    await initialize_agent(config)
    
    entities = [
        "FCCS_Total Geography",
        "Industrial Segment", 
        "Energy Segment", 
        "Fire Protection Segment", 
        "Administrative Segment",
        "VENT",
        "CVNT",
        "Elim",
        "Total Monumental",
        "Total MSC"
    ]
    
    print(f"{'Entity':<30} | {'Assets':>15} | {'Liab+Eq':>15} | {'Difference':>15}")
    print("-" * 80)
    
    for ent in entities:
        try:
            # Get Total Assets
            assets_res = await smart_retrieve(
                account="FCCS_Total Assets",
                entity=ent,
                period="Jun",
                years="FY25",
                scenario="Actual"
            )
            assets = 0.0
            if assets_res.get("status") == "success" and assets_res["data"].get("rows"):
                assets = float(assets_res["data"]["rows"][0]["data"][0] or 0.0)
            
            # Get Total Liabilities and Equity
            liab_res = await smart_retrieve(
                account="FCCS_Total Liabilities and Equity",
                entity=ent,
                period="Jun",
                years="FY25",
                scenario="Actual"
            )
            liab = 0.0
            if liab_res.get("status") == "success" and liab_res["data"].get("rows"):
                liab = float(liab_res["data"]["rows"][0]["data"][0] or 0.0)
            
            diff = assets - liab
            
            if abs(diff) > 0.01:
                print(f"{ent:<30} | {assets:15.2f} | {liab:15.2f} | {diff:15.2f} (UNBALANCED)")
            else:
                print(f"{ent:<30} | {assets:15.2f} | {liab:15.2f} | {diff:15.2f} (BALANCED)")
                
        except Exception as e:
            print(f"Error checking {ent}: {e}")

    await close_agent()

if __name__ == "__main__":
    asyncio.run(check_unbalanced())

