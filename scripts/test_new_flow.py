from fccs_agent.intelligence.planner import FCCSPlanner

def test_planner_new_flow():
    planner = FCCSPlanner()
    intent = "data_retrieval"
    entities = {"account": "FCCS_Net Income", "entity": "E501"}
    available_tools = ["smart_retrieve", "query_local_metadata", "get_application_info"]
    query = "What is the net income for E501?"
    
    print(f"Creating plan for query: {query}")
    plan = planner.create_plan(intent, entities, available_tools, user_query=query)
    print(f"Plan: {plan.name}")
    for step in plan.steps:
        print(f"  Step {step.id}: {step.tool_name} - {step.description}")
        print(f"    Params: {step.parameters}")

if __name__ == "__main__":
    test_planner_new_flow()

