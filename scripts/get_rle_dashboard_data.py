
import sqlite3
import json
from datetime import datetime

def get_rl_dashboard():
    conn = sqlite3.connect('data/fccs_agent.db')
    cursor = conn.cursor()
    
    stats = {}
    
    # Get total episodes
    cursor.execute("SELECT COUNT(*) FROM rl_episodes")
    stats['total_episodes'] = cursor.fetchone()[0]
    
    # Get outcomes
    cursor.execute("SELECT outcome, COUNT(*) FROM rl_episodes GROUP BY outcome")
    stats['outcomes'] = dict(cursor.fetchall())
    
    # Get average reward
    cursor.execute("SELECT AVG(episode_reward) FROM rl_episodes")
    stats['avg_reward'] = cursor.fetchone()[0] or 0.0
    
    # Get top 5 successful tool sequences
    cursor.execute("SELECT tool_sequence, episode_reward FROM rl_episodes WHERE outcome='success' ORDER BY episode_reward DESC LIMIT 5")
    stats['top_sequences'] = []
    for row in cursor.fetchall():
        try:
            stats['top_sequences'].append({
                "sequence": json.loads(row[0]),
                "reward": row[1]
            })
        except:
            pass
            
    # Get latest metrics
    cursor.execute("SELECT metric_name, AVG(metric_value) FROM rl_metrics GROUP BY metric_name")
    stats['metrics'] = dict(cursor.fetchall())
    
    # Get exploration stats if available
    cursor.execute("SELECT metric_value FROM rl_metrics WHERE metric_name='exploration_rate' ORDER BY timestamp DESC LIMIT 1")
    row = cursor.fetchone()
    stats['current_exploration_rate'] = row[0] if row else "N/A"
    
    conn.close()
    return stats

if __name__ == "__main__":
    try:
        dashboard_data = get_rl_dashboard()
        print(json.dumps(dashboard_data, indent=2))
    except Exception as e:
        print(f"Error: {e}")

