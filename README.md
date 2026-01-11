# Anthropic FCCS Agent

This project is an independent FastMCP-based server for the FCCS toolset with an agentic pipeline powered by Anthropic Claude.

## What is included
- FastMCP stdio server for Claude Desktop or Cursor
- FastMCP HTTP (streamable) server for shared deployments
- Tool set for Oracle FCCS (Financial Consolidation and Close)
- Agentic pipeline using Anthropic Claude for intelligent planning and tool selection

## Quick start
1) Create a virtual environment and install dependencies:
```bash
python -m venv venv
.\venv\Scripts\Activate.ps1  # Windows
pip install -e .
```

2) Configure `.env` with your credentials:
```env
FCCS_URL=https://your-epm-instance.oraclecloud.com
FCCS_USERNAME=your-username
FCCS_PASSWORD=your-password
ANTHROPIC_API_KEY=your-anthropic-api-key
```

3) Run stdio or HTTP server:
```bash
# stdio MCP server
fccs-fastmcp-stdio

# HTTP MCP server (streamable HTTP)
fccs-fastmcp-http
```

## Configuration
Key environment variables:
- `FCCS_URL`, `FCCS_USERNAME`, `FCCS_PASSWORD` - Oracle FCCS credentials
- `FCCS_MOCK_MODE=true` to run without live FCCS connection
- `ANTHROPIC_API_KEY` - Anthropic API key for Claude
- `MODEL_ID` - Claude model to use (default: `claude-opus-4-20250514`)
- `DATABASE_URL` - SQLite database for feedback/RL services
- `FASTMCP_HOST`, `FASTMCP_PORT` - Server binding

## Agentic pipeline
The pipeline uses Anthropic Claude for intelligent planning and tool selection:
- Converts MCP tool definitions to Claude's tool use format
- Uses Claude's native tool calling for query analysis and planning
- Falls back to a heuristic planner if Anthropic API is unavailable

## Reinforcement Learning
The agent includes RL capabilities for improving tool recommendations:
- `RL_ENABLED=true` - Enable RL-based recommendations
- `RL_EXPLORATION_RATE` - Probability of exploring new actions
- `RL_LEARNING_RATE` - Q-value update speed
