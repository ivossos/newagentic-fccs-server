
import asyncio
from fccs_agent.config import load_config
from fccs_agent.services.feedback_service import init_feedback_service
from fccs_agent.services.rl_service import init_rl_service, get_rl_service
import json

async def show_stats():
    config = load_config()
    feedback_service = init_feedback_service(config.database_url)
    rl_service = init_rl_service(
        feedback_service,
        config.database_url,
        exploration_rate=config.rl_exploration_rate,
        learning_rate=config.rl_learning_rate,
        discount_factor=config.rl_discount_factor,
        min_samples=config.rl_min_samples
    )
    
    stats = rl_service.get_learning_stats()
    
    # Also get top sequences
    top_sequences = rl_service.get_successful_sequences(limit=5)
    stats['top_sequences'] = top_sequences
    
    print(json.dumps(stats, indent=2))

if __name__ == "__main__":
    asyncio.run(show_stats())

