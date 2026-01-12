# Windows Deployment Guide - FCCS FastMCP Agent

Complete guide for installing and deploying the FCCS FastMCP Agent on Windows systems.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Installation](#2-installation)
3. [Configuration](#3-configuration)
4. [Running the Application](#4-running-the-application)
5. [Claude Desktop Integration](#5-claude-desktop-integration)
6. [Docker Deployment](#6-docker-deployment)
7. [VS Code Setup](#7-vs-code-setup)
8. [Troubleshooting](#8-troubleshooting)

---

## 1. Prerequisites

### System Requirements

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| OS | Windows 10 | Windows 11 |
| Python | 3.10 | 3.11+ |
| RAM | 4 GB | 8 GB |
| Disk | 500 MB | 1 GB |

### Install Python

1. Download Python from [python.org](https://www.python.org/downloads/)
2. During installation, check **"Add Python to PATH"**
3. Verify installation:

```powershell
python --version
# Expected: Python 3.10.x or higher
```

### Install Git (Optional)

Download from [git-scm.com](https://git-scm.com/download/win) if you need to clone the repository.

---

## 2. Installation

### Step 1: Navigate to Project Directory

```powershell
cd C:\Users\ivoss\Downloads\Projetos\agentic\newagentic-fccs-server
```

### Step 2: Create Virtual Environment

```powershell
# Create virtual environment
python -m venv venv
```

### Step 3: Activate Virtual Environment

**PowerShell:**
```powershell
.\venv\Scripts\Activate.ps1
```

**Command Prompt:**
```cmd
venv\Scripts\activate.bat
```

> **Note:** If you get an execution policy error in PowerShell, run:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

### Step 4: Upgrade pip

```powershell
python -m pip install --upgrade pip
```

### Step 5: Install Dependencies

```powershell
# Install the package with all dependencies
pip install -e .

# Optional: Install development dependencies
pip install -e ".[dev]"
```

### Step 6: Initialize Database

```powershell
# Create data directory if it doesn't exist
New-Item -ItemType Directory -Force -Path data

# Initialize the database
python -m fccs_agent.services.init_db
```

---

## 3. Configuration

### Create Environment File

Create a `.env` file in the project root with the following settings:

```ini
# ===========================================
# FCCS Connection Settings
# ===========================================
FCCS_URL=https://your-epm-instance.oraclecloud.com
FCCS_USERNAME=your_username
FCCS_PASSWORD=your_password
FCCS_API_VERSION=v3
FCCS_MOCK_MODE=false

# ===========================================
# Database Configuration
# ===========================================
DATABASE_URL=sqlite:///./data/fccs_agent.db

# ===========================================
# API Keys
# ===========================================
GOOGLE_API_KEY=your_google_api_key
MODEL_ID=gemini-2.0-flash
ANTHROPIC_API_KEY=your_anthropic_api_key

# ===========================================
# Server Configuration
# ===========================================
PORT=8080
FASTMCP_HOST=127.0.0.1
FASTMCP_PORT=8000
CORS_ORIGINS=http://localhost:3000,http://localhost:8080

# ===========================================
# Guardrails (Safety Settings)
# ===========================================
FCCS_SKIP_CONFIRMATION=false
FCCS_TRUSTED_RULES=Consolidate,Force Consolidate,Translate,Force Translate
FCCS_TRUSTED_OPERATIONS=

# ===========================================
# Reinforcement Learning
# ===========================================
RL_ENABLED=true
RL_EXPLORATION_RATE=0.1
RL_LEARNING_RATE=0.3
RL_DISCOUNT_FACTOR=0.95
RL_MIN_SAMPLES=3
```

### Configuration Options Explained

| Variable | Description | Default |
|----------|-------------|---------|
| `FCCS_URL` | Oracle EPM Cloud URL | Required |
| `FCCS_USERNAME` | Login username | Required |
| `FCCS_PASSWORD` | Login password | Required |
| `FCCS_MOCK_MODE` | Use mock data (no real EPM) | `false` |
| `DATABASE_URL` | SQLite or PostgreSQL URL | `sqlite:///./data/fccs_agent.db` |
| `RL_ENABLED` | Enable reinforcement learning | `true` |

---

## 4. Running the Application

Always activate the virtual environment first:

```powershell
.\venv\Scripts\Activate.ps1
```

### Option A: MCP Server (stdio) - For Claude Desktop

```powershell
python -m cli.fastmcp_stdio
```

Or use the installed command:
```powershell
fccs-fastmcp-stdio
```

### Option B: MCP Server (HTTP) - Streamable HTTP

```powershell
python -m web.fastmcp_http
```

Or use the installed command:
```powershell
fccs-fastmcp-http
```

Server starts at: `http://127.0.0.1:8000`

### Option C: REST API Server (FastAPI)

```powershell
uvicorn web.rest_api:app --reload --host 0.0.0.0 --port 8080
```

Access points:
- API: `http://localhost:8080`
- Docs: `http://localhost:8080/docs`
- OpenAPI: `http://localhost:8080/openapi.json`

### Option D: RL Dashboard

```powershell
python -m web.rle_dashboard
```

Access at: `http://localhost:8080/rl/dashboard`

---

## 5. Claude Desktop Integration

### Step 1: Locate Claude Config File

Open File Explorer and navigate to:
```
%APPDATA%\Claude\
```

Or press `Win + R` and type:
```
%APPDATA%\Claude
```

### Step 2: Edit claude_desktop_config.json

Create or edit `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "fccs-agent": {
      "command": "C:\\Users\\ivoss\\Downloads\\Projetos\\agentic\\newagentic-fccs-server\\venv\\Scripts\\python.exe",
      "args": ["-m", "cli.fastmcp_stdio"],
      "cwd": "C:\\Users\\ivoss\\Downloads\\Projetos\\agentic\\newagentic-fccs-server",
      "env": {
        "FCCS_URL": "https://your-epm-instance.oraclecloud.com",
        "FCCS_USERNAME": "your_username",
        "FCCS_PASSWORD": "your_password",
        "FCCS_API_VERSION": "v3",
        "FCCS_MOCK_MODE": "false",
        "DATABASE_URL": "sqlite:///./data/fccs_agent.db",
        "MODEL_ID": "gemini-2.0-flash",
        "GOOGLE_API_KEY": "your_google_api_key",
        "RL_ENABLED": "true"
      }
    }
  }
}
```

> **Important:** Use double backslashes (`\\`) in Windows paths within JSON.

### Step 3: Restart Claude Desktop

Close and reopen Claude Desktop to load the new configuration.

### Step 4: Verify Connection

In Claude Desktop, you should see the FCCS tools available. Try asking:
- "List available FCCS entities"
- "Show application details"

---

## 6. Docker Deployment

### Prerequisites

Install [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/)

### Build Image

```powershell
docker build -t fccs-fastmcp-agent:latest .
```

### Run Container

```powershell
docker run -d `
  --name fccs-agent `
  -p 8080:8080 `
  -e FCCS_URL="https://your-epm-instance.oraclecloud.com" `
  -e FCCS_USERNAME="your_username" `
  -e FCCS_PASSWORD="your_password" `
  -e GOOGLE_API_KEY="your_google_api_key" `
  -e ANTHROPIC_API_KEY="your_anthropic_api_key" `
  -v ${PWD}/data:/app/data `
  fccs-fastmcp-agent:latest
```

### Docker Commands

```powershell
# View logs
docker logs fccs-agent

# Stop container
docker stop fccs-agent

# Start container
docker start fccs-agent

# Remove container
docker rm fccs-agent

# View running containers
docker ps
```

---

## 7. VS Code Setup

### Recommended Extensions

Install these VS Code extensions:
- Python (ms-python.python)
- Pylance (ms-python.vscode-pylance)
- Python Debugger (ms-python.debugpy)

### Debug Configurations

The project includes pre-configured debug settings in `.vscode/launch.json`:

1. **FastMCP Server (stdio)** - Debug MCP stdio server
2. **FastMCP Server (HTTP)** - Debug HTTP server
3. **Python: Current File** - Debug any Python file

### Start Debugging

1. Open VS Code in the project folder
2. Press `F5` or go to Run > Start Debugging
3. Select the desired configuration

---

## 8. Troubleshooting

### Virtual Environment Issues

**Problem:** PowerShell blocks script execution

```powershell
# Solution: Change execution policy
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# Then retry activation
.\venv\Scripts\Activate.ps1
```

**Problem:** Virtual environment not recognized

```powershell
# Solution: Use full path
& "C:\Users\ivoss\Downloads\Projetos\agentic\newagentic-fccs-server\venv\Scripts\Activate.ps1"
```

### Port Already in Use

**Problem:** Port 8080 is already in use

```powershell
# Find the process using the port
netstat -ano | findstr :8080

# Kill the process (replace <PID> with the actual PID)
taskkill /PID <PID> /F
```

### Database Issues

**Problem:** Database locked error

```powershell
# Solution 1: Close any open database connections (SQLite browsers, etc.)

# Solution 2: Delete journal files
Remove-Item data\*.db-journal -Force

# Solution 3: Reinitialize database
Remove-Item data\fccs_agent.db -Force
python -m fccs_agent.services.init_db
```

### Module Import Errors

**Problem:** Module not found

```powershell
# Verify venv is activated (should show (venv) in prompt)
.\venv\Scripts\Activate.ps1

# Reinstall package
pip install -e .

# Check installed packages
pip list | findstr fccs
```

### Connection Issues

**Problem:** Cannot connect to FCCS

1. Verify credentials in `.env` file
2. Test the URL in a browser
3. Check firewall/proxy settings
4. Enable mock mode for testing:
   ```ini
   FCCS_MOCK_MODE=true
   ```

### SSL Certificate Errors

**Problem:** SSL verification failed

```powershell
# Temporary workaround (not recommended for production)
$env:REQUESTS_CA_BUNDLE=""
$env:CURL_CA_BUNDLE=""
```

---

## Quick Reference

### Common Commands

```powershell
# Activate environment
.\venv\Scripts\Activate.ps1

# Run MCP server (stdio)
python -m cli.fastmcp_stdio

# Run HTTP server
python -m web.fastmcp_http

# Run REST API
uvicorn web.rest_api:app --reload --port 8080

# Run tests
pytest

# Check environment
python scripts\check_env.py

# View RL statistics
python scripts\show_rl_stats.py
```

### Project Structure

```
newagentic-fccs-server/
├── fccs_agent/          # Main agent package
│   ├── tools/           # MCP tools
│   ├── services/        # Business logic
│   └── client/          # FCCS API client
├── cli/                 # CLI entry points
├── web/                 # Web servers
├── data/                # SQLite database
├── scripts/             # Utility scripts
├── .env                 # Environment config
└── pyproject.toml       # Dependencies
```

### Available MCP Tools

| Tool | Description |
|------|-------------|
| `run_business_rule` | Execute FCCS business rules |
| `copy_data` | Copy data between accounts |
| `check_data_status` | Verify data status |
| `check_consolidation_status` | Consolidation status |
| `list_entities` | List available entities |
| `list_dimensions` | List dimensions |
| `get_job_status` | Monitor job execution |
| `list_journals` | List journals |
| `generate_report` | Generate reports |
| `provide_feedback` | Submit feedback for RL |

---

## Support

For issues and feature requests:
- Check existing [GitHub Issues](https://github.com/anthropics/claude-code/issues)
- Review the [REINFORCEMENT_LEARNING.md](./REINFORCEMENT_LEARNING.md) for RL details

---

*Last updated: January 2026*
