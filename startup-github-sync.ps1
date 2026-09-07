<# Synchronizes the Desktop workspace after the legacy scheduled tasks finish. #>
$ErrorActionPreference = 'Stop'
Start-Sleep -Seconds 240
& (Join-Path $PSScriptRoot 'sync-github.ps1')
