<# Safely backs up code changes to GitHub while Windows is running. #>
$ErrorActionPreference = 'Stop'
Start-Sleep -Seconds 75
while ($true) {
    # Run the worker in a child PowerShell process because sync-github.ps1
    # intentionally uses `exit` for its safe success/failure statuses.
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'sync-github.ps1')
    Start-Sleep -Seconds 300
}
