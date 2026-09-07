<# Starts the Desktop workspace after Windows sign-in without a visible window. #>
$ErrorActionPreference = 'Stop'
Start-Sleep -Seconds 190
& (Join-Path $PSScriptRoot 'start-local.ps1')
