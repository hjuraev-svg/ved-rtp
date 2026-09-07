<#
.SYNOPSIS
    Backs up and deploys the current Git commit to the sole public VED server.

.DESCRIPTION
    The script never uploads `.env`, never changes Docker volumes, and creates
    a dated PostgreSQL + uploads backup on the server before replacing code.
    It uses the dedicated local deployment key automatically.

.EXAMPLE
    .\deploy-public.ps1
#>

[CmdletBinding()]
param(
    [string]$HostName = 'ubuntu@176.96.241.39',
    [string]$RemoteDir = '~/ved',
    [string]$PublicUrl = 'https://jnslabsonline.uz/ved',
    [switch]$SkipBackup
)

$ErrorActionPreference = 'Stop'
$repoPath = $PSScriptRoot
$keyPath = Join-Path $env:USERPROFILE '.ssh\ved_rtp_deploy'
$runtimeDir = Join-Path $repoPath '.runtime'
$archivePath = Join-Path $runtimeDir 'public-deploy.tar'
$sshArgs = @('-i', $keyPath, '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15')

function Invoke-Remote([string]$command) {
    & ssh @sshArgs $HostName $command
    if ($LASTEXITCODE -ne 0) { throw "Remote command failed (exit code $LASTEXITCODE)." }
}

if (-not (Test-Path -LiteralPath $keyPath -PathType Leaf)) {
    throw "Deployment key was not found: $keyPath"
}
if (-not (git -C $repoPath status --porcelain)) {
    # A clean working tree is required: `git archive HEAD` deploys exactly the
    # reviewed and GitHub-saved commit, never uncommitted files.
} else {
    throw 'Local changes are not committed. Commit and push them before deployment.'
}

New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null

Write-Host '1/5  Checking public-server access…'
Invoke-Remote "set -eu; mkdir -p $RemoteDir; test -d $RemoteDir"

if (-not $SkipBackup) {
    Write-Host '2/5  Creating remote database and uploads backups…'
    Invoke-Remote "set -eu; cd $RemoteDir; mkdir -p backups; stamp=`$(date +%Y%m%d-%H%M%S); docker compose exec -T db sh -lc 'pg_dump -U `"`$POSTGRES_USER`" `"`$POSTGRES_DB`"' > `"backups/postgres-`$stamp.sql`"; docker run --rm -v ved-rtp_uploads:/source:ro -v `"`$(pwd)/backups`":/backup alpine:3.20 tar -C /source -czf `"/backup/uploads-`$stamp.tgz`" ."
}

Write-Host '3/5  Packaging the committed Git version…'
Remove-Item -LiteralPath $archivePath -Force -ErrorAction SilentlyContinue
& git -C $repoPath archive --format=tar --output=$archivePath HEAD
if ($LASTEXITCODE -ne 0) { throw 'Could not create deployment archive.' }

try {
    Write-Host '4/5  Uploading code and rebuilding public containers…'
    & scp @sshArgs $archivePath "${HostName}:/tmp/ved-rtp-deploy.tar"
    if ($LASTEXITCODE -ne 0) { throw 'Could not upload deployment archive.' }
    Invoke-Remote "set -eu; cd $RemoteDir; tar -xf /tmp/ved-rtp-deploy.tar -C $RemoteDir; rm -f /tmp/ved-rtp-deploy.tar; docker compose up -d --build --wait --wait-timeout 180"
}
finally {
    Remove-Item -LiteralPath $archivePath -Force -ErrorAction SilentlyContinue
}

Write-Host '5/5  Verifying public health…'
$health = Invoke-RestMethod -Uri "$PublicUrl/api/health" -TimeoutSec 30
if ($health.status -ne 'ok' -or -not $health.database) {
    throw "Public health check failed: $($health | ConvertTo-Json -Compress)"
}
Write-Host "Deployment completed. Public API and database are healthy: $PublicUrl"
