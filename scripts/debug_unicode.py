import asyncio
import sys
from fccs_agent.agent import initialize_agent, agentic_query, close_agent

async def main():
    try:
        await initialize_agent()
        result = await agentic_query('get app info')
        print(result)
    except Exception as e:
        print(f"Caught error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await close_agent()

if __name__ == "__main__":
    asyncio.run(main())

