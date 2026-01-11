import asyncio
import sys
from fccs_agent.agent import initialize_agent, close_agent
from fccs_agent.tools.data import smart_retrieve

async def test():
    await initialize_agent()
    print(await smart_retrieve(account='FCCS_Net Income', entity='Industrial Segment', period='Dec', years='FY24', scenario='Actual'))
    await close_agent()

if __name__ == "__main__":
    asyncio.run(test())

