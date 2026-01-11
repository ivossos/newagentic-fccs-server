
import asyncio
from fccs_agent.intelligence.planner import FCCSPlanner

def test_planner():
    planner = FCCSPlanner()
    intent = "data_retrieval"
    entities = {}
    available_tools = ["smart_retrieve", "get_application_info"]
    print(f"Creating plan for: {intent}")
    plan = planner.create_plan(intent, entities, available_tools)
    print(f"Plan: {plan.name}")
    print(f"Steps: {[s.tool_name for s in plan.steps]}")

if __name__ == "__main__":
    test_planner()

