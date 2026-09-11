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

function Test-DockerReady {
    # `docker info` against a stopped engine writes to stderr. Under
    # $ErrorActionPreference = 'Stop', PowerShell 5.1 turns a native command's
    # redirected stderr into a *terminating* NativeCommandError — so probing a
    # stopped engine aborted the whole script instead of entering the wait loop
    # below. That is why nothing came up on mornings when Docker was not already
    # running. Drop to 'Continue' for the probe and judge only by exit code.
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $dockerPath info 2>&1 | Out-Null
        return $LASTEXITCODE -eq 0
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
}

try {
    if (-not $dockerPath) {
        throw 'Docker CLI was not found. Install or start Docker Desktop first.'
    }

    # Start the engine ourselves rather than relying on Docker Desktop's own
    # "start on login" setting. That setting lives in settings-store.json, which
    # Docker rewrites when it exits, so it cannot be trusted to survive a
    # shutdown — and when it is off, nothing brings the stack up in the morning.
    $ready = Test-DockerReady
    if (-not $ready) {
        $desktop = @(
            "$env:LOCALAPPDATA\Programs\DockerDesktop\Docker Desktop.exe",
            "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
        ) | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
        if ($desktop) {
            Write-AppLog "Docker engine is down; launching $desktop"
            Start-Process -FilePath $desktop | Out-Null
        }
        else {
            Write-AppLog 'Docker Desktop executable not found; waiting in case it is already starting.'
        }

        # A cold boot of the engine is slower than a warm one, so allow ten minutes.
        $deadline = (Get-Date).AddMinutes(10)
        while (-not $ready -and (Get-Date) -lt $deadline) {
            Start-Sleep -Seconds 10
            $ready = Test-DockerReady
        }
    }

    if (-not $ready) {
        throw 'Docker Desktop did not become ready within ten minutes.'
    }
    Write-AppLog 'Docker engine is ready.'

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
