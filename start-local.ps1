<#
.SYNOPSIS
    Starts the local VED RTP stack and verifies its health.

.DESCRIPTION
    Designed for Windows Task Scheduler. It waits for Docker Desktop after
    sign-in, rebuilds the current source, starts the Compose services and logs
    the result outside the Git repository.
#>

$ErrorActionPreference = 'Stop'

$repoPath = $PSScriptRoot
$logDir = Join-Path $repoPath '.runtime'
$logPath = Join-Path $logDir 'local-app.log'
$dockerPath = @(
    (Get-Command docker -ErrorAction SilentlyContinue).Source,
    "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe",
    "$env:ProgramFiles\Docker\Docker\resources\bin\docker.exe",
    "$env:LOCALAPPDATA\Docker\Docker\resources\bin\docker.exe"
) | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } | Select-Object -First 1

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Write-AppLog([string]$message) {
    Add-Content -LiteralPath $logPath -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $message"
}

function Invoke-Docker([string[]]$arguments) {
    # Docker Compose writes normal build progress to stderr. Temporarily allow
    # that stream so PowerShell does not treat a successful build as an error.
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = & $dockerPath @arguments 2>&1
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    foreach ($line in $output) {
        if ($line) { Write-AppLog $line.ToString() }
    }
    if ($exitCode -ne 0) {
        throw "docker $($arguments -join ' ') failed with exit code $exitCode"
    }
}

try {
    if (-not $dockerPath) {
        throw 'Docker CLI was not found. Install or start Docker Desktop first.'
    }

    $deadline = (Get-Date).AddMinutes(5)
    do {
        & $dockerPath info 1>$null 2>$null
        if ($LASTEXITCODE -eq 0) { break }
        Start-Sleep -Seconds 10
    } while ((Get-Date) -lt $deadline)

    if ($LASTEXITCODE -ne 0) {
        throw 'Docker Desktop did not become ready within five minutes.'
    }

    $composeFile = Join-Path $repoPath 'docker-compose.yml'
    Invoke-Docker @('compose', '--project-directory', $repoPath, '-f', $composeFile, 'up', '-d', '--build', '--wait', '--wait-timeout', '120')
    $webPort = ((Get-Content (Join-Path $repoPath '.env') |
        Where-Object { $_ -match '^WEB_PORT=' } |
        Select-Object -First 1) -replace '^WEB_PORT=', '').Trim()
    if (-not $webPort) { $webPort = '8090' }

    $health = Invoke-RestMethod -Uri "http://localhost:$webPort/api/health" -TimeoutSec 15
    if ($health.status -ne 'ok') {
        throw "API health endpoint returned status '$($health.status)'."
    }
    Write-AppLog "Local stack is healthy at http://localhost:$webPort (API: $($health.status))."
}
catch {
    Write-AppLog "Local start failed: $($_.Exception.Message)"
    exit 1
}
