$ErrorActionPreference = "Stop"

$procs = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
    Where-Object { $_.CommandLine -like "*cli.fastmcp_stdio*" }

foreach ($proc in $procs) {
    Stop-Process -Id $proc.ProcessId -Force
}
