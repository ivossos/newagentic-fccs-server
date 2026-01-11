
import asyncio
from fccs_agent.intelligence.context_memory import ContextMemory
from fccs_agent.config import load_config

def test_context():
    config = load_config()
    memory = ContextMemory(config.database_url)
    session_id = "test_session"
    print(f"Loading POV for: {session_id}")
    pov = memory.get_pov(session_id)
    print(f"POV: {pov}")

if __name__ == "__main__":
    test_context()

