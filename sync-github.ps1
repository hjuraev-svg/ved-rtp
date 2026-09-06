<#
.SYNOPSIS
    Commits and pushes non-ignored changes in this repository to GitHub.

.DESCRIPTION
    This script is intended to be run by Windows Task Scheduler after sign-in.
    It never performs reset or rebase. A remote-only fast-forward update is
    applied only when the working tree is clean. If both the remote and local
    copy changed, it stops safely and records the reason in the log.
#>

$ErrorActionPreference = 'Stop'

$repoPath = $PSScriptRoot
$logDir = Join-Path $repoPath '.runtime'
$logPath = Join-Path $logDir 'github-sync.log'
$mutex = New-Object System.Threading.Mutex($false, 'Local\VED-RTP-GitHubAutoSync')
$hasSyncLock = $false

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
    if (-not $mutex.WaitOne(0)) {
        Write-SyncLog 'Another sync is already running.'
        exit 0
    }
    $hasSyncLock = $true

    Invoke-Git @('rev-parse', '--is-inside-work-tree')

    # Check the remote before committing. This prevents an unattended task
    # from attempting a merge when the same repository was changed elsewhere.
    & git -C $repoPath fetch --quiet origin main
    $remoteAvailable = $LASTEXITCODE -eq 0
    if ($remoteAvailable) {
        $remoteAhead = [int](& git -C $repoPath rev-list --count 'HEAD..origin/main')
        $workTreeDirty = [bool](& git -C $repoPath status --porcelain)
        if ($remoteAhead -gt 0) {
            if ($workTreeDirty) {
                Write-SyncLog 'Sync paused: origin/main changed and local work is present. Resolve it manually before the next sync.'
                exit 3
            }
            Invoke-Git @('merge', '--ff-only', 'origin/main')
            Write-SyncLog 'Applied a safe fast-forward update from origin/main.'
        }
    }
    else {
        Write-SyncLog 'GitHub is unavailable; local changes will be committed and pushed on a later run.'
    }

    Invoke-Git @('add', '--all')

    & git -C $repoPath diff --cached --quiet
    if ($LASTEXITCODE -eq 0) {
        Write-SyncLog 'No local changes to sync.'
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
    if ($remoteAvailable) {
        Invoke-Git @('push', 'origin', 'main')
        Write-SyncLog 'Changes committed and pushed to origin/main.'
    }
    else {
        Write-SyncLog 'Changes committed locally; push is deferred until GitHub is reachable.'
    }
}
catch {
    Write-SyncLog "Sync failed: $($_.Exception.Message)"
    exit 1
}
finally {
    if ($mutex) {
        if ($hasSyncLock) { $mutex.ReleaseMutex() }
        $mutex.Dispose()
    }
}
