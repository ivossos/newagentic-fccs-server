import fccs_agent.intelligence.planner as planner
import inspect

print(f"File: {planner.__file__}")
with open(planner.__file__, "r") as f:
    content = f.read()
    if "Standard Data Retrieval TEST" in content:
        print("Found Standard Data Retrieval TEST in file")
    else:
        print("NOT found Standard Data Retrieval TEST in file")
        if "Simple Data Retrieval" in content:
            print("Found Simple Data Retrieval in file")

from fccs_agent.intelligence.planner import FCCSPlanner
p = FCCSPlanner()
print(f"PATTERNS keys: {p.PATTERNS.keys()}")
if "simple_data_retrieval" in p.PATTERNS:
    print(f"simple_data_retrieval name: {p.PATTERNS['simple_data_retrieval']['name']}")

