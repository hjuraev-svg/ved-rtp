<#!
.SYNOPSIS
    Commits and pushes non-ignored changes in this repository to GitHub.

.DESCRIPTION
    This script is intended to be run by Windows Task Scheduler after sign-in.
    It deliberately never performs pull, rebase, reset, or any merge: if the
    remote branch has changed elsewhere, it leaves the local work untouched and
    records the failed push in the log for manual resolution.
#>

$ErrorActionPreference = 'Stop'

$repoPath = $PSScriptRoot
$logDir = Join-Path $env:LOCALAPPDATA 'VED-RTP'
$logPath = Join-Path $logDir 'github-sync.log'

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Write-SyncLog([string]$message) {
    Add-Content -LiteralPath $logPath -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $message"
}

function Invoke-Git([string[]]$arguments) {
    & git -C $repoPath @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "git $($arguments -join ' ') failed with exit code $LASTEXITCODE"
    }
}

try {
    Invoke-Git @('rev-parse', '--is-inside-work-tree')
    Invoke-Git @('add', '--all')

    & git -C $repoPath diff --cached --quiet
    if ($LASTEXITCODE -eq 0) {
        Write-SyncLog 'No changes to sync.'
        exit 0
    }
    if ($LASTEXITCODE -ne 1) {
        throw "git diff --cached --quiet failed with exit code $LASTEXITCODE"
    }

    # A small last-resort guard for common credential formats before a public push.
    $secretPattern = 'AIza[0-9A-Za-z_-]{35}|ghp_[0-9A-Za-z]{36}|github_pat_[0-9A-Za-z_]{20,}|xox[baprs]-|-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----'
    $stagedFiles = & git -C $repoPath diff --cached --name-only --diff-filter=ACMR
    foreach ($relativePath in $stagedFiles) {
        $fullPath = Join-Path $repoPath $relativePath
        if ((Test-Path -LiteralPath $fullPath -PathType Leaf) -and
            (Select-String -LiteralPath $fullPath -Pattern $secretPattern -Quiet -ErrorAction SilentlyContinue)) {
            Write-SyncLog "Sync blocked: a possible secret was found in $relativePath."
            exit 2
        }
    }

    $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Invoke-Git @('commit', '-m', "Auto-sync: $stamp")
    Invoke-Git @('push', 'origin', 'main')
    Write-SyncLog 'Changes committed and pushed to origin/main.'
}
catch {
    Write-SyncLog "Sync failed: $($_.Exception.Message)"
    exit 1
}
