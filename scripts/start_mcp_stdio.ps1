$ErrorActionPreference = "Stop"

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

if (-not $env:DATABASE_URL) {
    $env:DATABASE_URL = "sqlite:///./data/fccs_agent.db"
}

try {
    $existing = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
        Where-Object { $_.CommandLine -like "*cli.fastmcp_stdio*" }
    foreach ($proc in $existing) {
        Stop-Process -Id $proc.ProcessId -Force
    }
} catch {
    # Ignore stop failures to allow startup
}

python -m cli.fastmcp_stdio
