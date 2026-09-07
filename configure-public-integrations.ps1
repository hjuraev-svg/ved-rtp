<#
.SYNOPSIS
    Safely configures Gmail and Telegram secrets on the public server.

.DESCRIPTION
    Secrets are requested interactively and are never stored in Git, command
    history, or script output. Run only after deploy-public.ps1 can connect.
#>

[CmdletBinding()]
param(
    [string]$HostName = 'ubuntu@176.96.241.39',
    [string]$RemoteDir = '~/ved',
    [string]$PublicBaseUrl = 'https://jnslabsonline.uz/ved'
)

$ErrorActionPreference = 'Stop'
$keyPath = Join-Path $env:USERPROFILE '.ssh\ved_rtp_deploy'
$sshArgs = @('-i', $keyPath, '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15')

function Get-PlainSecret([string]$prompt) {
    $secure = Read-Host $prompt -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}

function New-UrlSafeSecret([int]$bytes = 32) {
    $buffer = New-Object byte[] $bytes
    [Security.Cryptography.RandomNumberGenerator]::Fill($buffer)
    return [Convert]::ToBase64String($buffer).Replace('+', '-').Replace('/', '_')
}

$gmailClientId = Read-Host 'Google OAuth Client ID'
$gmailClientSecret = Get-PlainSecret 'Google OAuth Client Secret'
$telegramBotToken = Get-PlainSecret 'Telegram BotFather token'
if (-not $gmailClientId -or -not $gmailClientSecret -or -not $telegramBotToken) {
    throw 'All three values are required.'
}

# Fernet requires a URL-safe base64 representation of exactly 32 random bytes.
$fernetKey = New-UrlSafeSecret 32
$webhookSecret = (New-UrlSafeSecret 32).TrimEnd('=')
$lines = @(
    "PUBLIC_BASE_URL=$PublicBaseUrl",
    "INTEGRATION_ENCRYPTION_KEY=$fernetKey",
    "GMAIL_CLIENT_ID=$gmailClientId",
    "GMAIL_CLIENT_SECRET=$gmailClientSecret",
    "GMAIL_REDIRECT_URI=$PublicBaseUrl/api/integrations/gmail/callback",
    'GMAIL_POLL_INTERVAL_MINUTES=5',
    "TELEGRAM_BOT_TOKEN=$telegramBotToken",
    "TELEGRAM_WEBHOOK_SECRET=$webhookSecret"
) -join "`n"
$payload = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($lines))

Write-Host 'Writing secrets to the server .env and restarting only the API…'
$remote = "set -eu; cd $RemoteDir; printf %s '$payload' | base64 -d > /tmp/ved-integrations.env; touch .env; while IFS= read -r line; do key=`${line%%=*}; sed -i `"/^`$key=/d`" .env; printf '%s\n' `"`$line`" >> .env; done < /tmp/ved-integrations.env; rm -f /tmp/ved-integrations.env; docker compose up -d --build --wait --wait-timeout 180"
& ssh @sshArgs $HostName $remote
if ($LASTEXITCODE -ne 0) { throw "Remote configuration failed (exit code $LASTEXITCODE)." }

$health = Invoke-RestMethod -Uri "$PublicBaseUrl/api/health" -TimeoutSec 30
if ($health.status -ne 'ok') { throw 'The public API did not become healthy after configuration.' }
Write-Host 'Configured. Sign in as administrator, open «Почта и Telegram», and click «Gmail подключить» then «Проверить Bot».'
