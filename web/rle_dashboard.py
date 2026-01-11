import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as graph_objects
import json
from datetime import datetime
import os
import sys

# Set page config
st.set_page_config(
    page_title="FCCS Agent - RLE Dashboard",
    page_icon="🧠",
    layout="wide"
)

# Database connection logic synchronized with agent config
project_root = os.getcwd()
if project_root not in sys.path:
    sys.path.append(project_root)

try:
    from fccs_agent.config import config
    DB_URL = config.database_url
    if DB_URL.startswith("sqlite:///"):
        # Strip sqlite:/// prefix
        db_file = DB_URL.replace("sqlite:///", "")
        # Resolve relative paths
        if db_file.startswith("./"):
            DB_PATH = os.path.join(project_root, db_file[2:])
        elif not os.path.isabs(db_file):
            DB_PATH = os.path.join(project_root, db_file)
        else:
            DB_PATH = db_file
    else:
        # Fallback to default path
        DB_PATH = os.path.join(project_root, 'data', 'fccs_agent.db')
except Exception as e:
    st.error(f"Error loading config: {e}. Falling back to default DB path.")
    DB_PATH = os.path.join(project_root, 'data', 'fccs_agent.db')

def get_connection():
    return sqlite3.connect(DB_PATH)

@st.cache_data(ttl=60)
def load_data(query):
    conn = get_connection()
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def main():
    st.title("🧠 FCCS Agent - Reinforcement Learning Engine (RLE) Dashboard")
    st.markdown("Monitoring tool selection optimization and agentic performance.")

    # Sidebar stats
    st.sidebar.header("System Status")
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Total episodes
        cursor.execute("SELECT COUNT(*) FROM rl_episodes")
        total_episodes = cursor.fetchone()[0]
        st.sidebar.metric("Total Episodes", total_episodes)
        
        # Avg reward
        cursor.execute("SELECT AVG(episode_reward) FROM rl_episodes")
        avg_reward = cursor.fetchone()[0] or 0.0
        st.sidebar.metric("Average Reward", f"{avg_reward:.2f}")
        
        # Exploration rate
        cursor.execute("SELECT metric_value FROM rl_metrics WHERE metric_name='exploration_rate' ORDER BY timestamp DESC LIMIT 1")
        row = cursor.fetchone()
        exploration_rate = row[0] if row else 0.1
        st.sidebar.metric("Current Exploration (ε)", f"{exploration_rate:.1%}")
        
        # Success rate
        cursor.execute("SELECT COUNT(*) FROM rl_episodes WHERE outcome='success'")
        success_count = cursor.fetchone()[0]
        success_rate = (success_count / total_episodes) if total_episodes > 0 else 0.0
        st.sidebar.metric("Success Rate", f"{success_rate:.1%}")
        
        conn.close()
    except Exception as e:
        st.sidebar.error(f"Error loading stats: {e}")

    # Tabs
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Overview", "🛠️ Tool Performance", "🧬 Learning Insights", "📋 Raw Data"])

    with tab1:
        st.header("Learning Progress Over Time")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Reward trend
            df_rewards = load_data("SELECT created_at, episode_reward FROM rl_episodes ORDER BY created_at")
            if not df_rewards.empty:
                df_rewards['created_at'] = pd.to_datetime(df_rewards['created_at'])
                fig = px.line(df_rewards, x='created_at', y='episode_reward', title="Episode Reward Trend",
                             labels={"created_at": "Time", "episode_reward": "Reward"})
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No episode data yet.")
                
        with col2:
            # TD Error trend
            df_metrics = load_data("SELECT timestamp, metric_value FROM rl_metrics WHERE metric_name='td_error' ORDER BY timestamp")
            if not df_metrics.empty:
                df_metrics['timestamp'] = pd.to_datetime(df_metrics['timestamp'])
                # Rolling mean for smoother chart
                df_metrics['rolling_error'] = df_metrics['metric_value'].rolling(window=10).mean()
                fig = px.line(df_metrics, x='timestamp', y='rolling_error', title="TD Error (Smoothing)",
                             labels={"timestamp": "Time", "rolling_error": "TD Error (Mean)"})
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No TD error metrics yet.")

        # Outcome distribution
        df_outcomes = load_data("SELECT outcome, COUNT(*) as count FROM rl_episodes GROUP BY outcome")
        if not df_outcomes.empty:
            fig = px.pie(df_outcomes, values='count', names='outcome', title="Episode Outcomes",
                        color_discrete_map={'success': 'green', 'partial': 'orange', 'failure': 'red'})
            st.plotly_chart(fig, use_container_width=True)

    with tab2:
        st.header("Tool Execution Metrics")
        
        df_tools = load_data("SELECT * FROM tool_metrics")
        if not df_tools.empty:
            col1, col2 = st.columns(2)
            
            with col1:
                # Success rate per tool
                df_tools['success_rate'] = df_tools['success_count'] / df_tools['total_calls']
                fig = px.bar(df_tools, x='tool_name', y='success_rate', title="Tool Success Rate",
                            color='success_rate', color_continuous_scale='RdYlGn')
                st.plotly_chart(fig, use_container_width=True)
                
            with col2:
                # Avg execution time
                fig = px.bar(df_tools, x='tool_name', y='avg_execution_time_ms', title="Avg Execution Time (ms)",
                            color='avg_execution_time_ms')
                st.plotly_chart(fig, use_container_width=True)
                
            st.subheader("Aggregated Tool Data")
            st.dataframe(df_tools, use_container_width=True)
        else:
            st.info("No tool metrics recorded yet.")

    with tab3:
        st.header("RL Learning Insights")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Top Successful Sequences")
            df_seq = load_data("SELECT sequence_key, count, avg_reward, success_rate FROM rl_tool_sequences ORDER BY avg_reward DESC LIMIT 10")
            if not df_seq.empty:
                st.dataframe(df_seq, use_container_width=True)
            else:
                st.info("No sequence data yet.")
                
        with col2:
            st.subheader("Top Q-Values (Policy)")
            df_policy = load_data("SELECT tool_name, context_hash, action_value, visit_count FROM rl_policy ORDER BY action_value DESC LIMIT 10")
            if not df_policy.empty:
                st.dataframe(df_policy, use_container_width=True)
            else:
                st.info("No policy data yet.")

        st.subheader("Context Exploration")
        df_exploration = load_data("SELECT timestamp, metric_value FROM rl_metrics WHERE metric_name='learning_confidence' ORDER BY timestamp")
        if not df_exploration.empty:
            df_exploration['timestamp'] = pd.to_datetime(df_exploration['timestamp'])
            fig = px.area(df_exploration, x='timestamp', y='metric_value', title="Learning Confidence Score",
                         labels={"timestamp": "Time", "metric_value": "Confidence"})
            st.plotly_chart(fig, use_container_width=True)

    with tab4:
        st.header("Recent Data Logs")
        
        st.subheader("Latest Episodes")
        df_eps = load_data("SELECT * FROM rl_episodes ORDER BY created_at DESC LIMIT 20")
        st.dataframe(df_eps, use_container_width=True)
        
        st.subheader("Latest Tool Executions")
        df_execs = load_data("SELECT id, session_id, tool_name, success, execution_time_ms, user_rating, created_at FROM tool_executions ORDER BY created_at DESC LIMIT 20")
        st.dataframe(df_execs, use_container_width=True)

if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        st.error(f"Database not found at {DB_PATH}. Please ensure the agent has been run at least once.")
    else:
        main()

