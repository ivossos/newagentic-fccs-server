
import asyncio
from fccs_agent.agent import initialize_agent, execute_tool
from fccs_agent.config import config

async def test_execution():
    print(f"Initializing agent with DB: {config.database_url}")
    await initialize_agent()
    
    print("Executing tool...")
    result = await execute_tool("get_application_info", {})
    print(f"Result status: {result.get('status')}")
    if "execution_id" in result:
        print(f"Execution ID: {result['execution_id']}")
    else:
        print("No execution_id in result")

if __name__ == "__main__":
    asyncio.run(test_execution())

