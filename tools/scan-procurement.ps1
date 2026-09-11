<#
  Dry-run scanner: derives structured procurement records from the folder tree.
  Writes JSON only. Touches nothing in the database and nothing on G:.
#>
param(
  # Root of the procurement archive, e.g. the "Import 2022-2026HJ" folder.
  # Passed in rather than hard-coded: the path contains a Drive share id.
  [Parameter(Mandatory = $true)][string]$Root,
  [string]$Out = (Join-Path $PSScriptRoot 'procurement.json')
)

$ErrorActionPreference = 'Stop'
$dateRx    = '^(\d{2})[.\-](\d{2})[.\-](\d{4})$'
# folder names that are organisational noise, never a supplier
$noiseRx   = '^(_Archive|_?\d{4}([-\u2013_]\d{2,4})*|draft|Rev|Final docs|new|NEW|old)$'

$countries = @{
  'CHINA'='Китай'; 'TURKEY'='Турция'; 'INDIA'='Индия'; 'EUROPE'='Европа'; 'RUS'='Россия'
  'Mexico'='Мексика'; 'UZBEKISTAN'='Узбекистан'; 'BELARUS'='Беларусь'; 'GERMANY'='Германия'
}
# supplier-name hints when the path carries no country level
$nameCountry = @(
  @{ rx='Guangzhou|Shenzhen|Ningbo|NINGBO|Foshan|Wenzhou|Jiangxi|Xi.an|Dongguan|Shanghai|Suzhou|Henan|China|\(HK\)|AILUSI|DANQ'; c='Китай' },
  @{ rx='Sarebekir|Saribekir|Kale Kimya|7M Valf|Turkey|Gulcicek|GULCHECHAK'; c='Турция' },
  @{ rx='Novaphene|India|IMCD India'; c='Индия' },
  @{ rx='Givaudan|Expressions|Technico|BASF|Angus|IMCD'; c='Европа' },
  @{ rx='SARL|L\.I\.D'; c='Франция' }
)

# document classification -> dashboard doc_type codes
$docRules = @(
  @{ code='gtd';               rx='ГТД|GTD|растаможк|деклараци|customs' },
  @{ code='cmr_bl';            rx='\bCMR\b|B/?L\b|коносамент|bill of lading|waybill|накладн|ТТН' },
  @{ code='cert_origin';       rx='^CO[\s._(\-]|\bCO\b|certificate of origin|сертификат происх|form a|\bСО\b' },
  @{ code='cert_quality';      rx='MSDS|analys|\bCOA\b|качеств|conformity|соответств|тест|test report' },
  @{ code='packing_list';      rx='packing|\bPL\b|упаковочн' },
  @{ code='invoice';           rx='\bCI\b|invoice|инвойс|счет|счёт' },
  @{ code='order_confirmation';rx='\bPI\b|proforma|проформа|order confirm' },
  @{ code='contract';          rx='contract|agreem|agrem|договор|контракт|spec|специфик|приложен|appendix' },
  @{ code='act_qc';            rx='^act|\bакт\b|приемк|приёмк' }
)
# service pipeline equivalents (Transportation)
$svcRules = @(
  @{ code='svc_payment'; rx='swift|оплат|payment|платеж|платёж' },
  @{ code='svc_act';     rx='^act|\bакт\b' },
  @{ code='svc_invoice'; rx='invoice|инвойс|счет|счёт|\bCI\b' },
  @{ code='svc_waybill'; rx='\bCMR\b|B/?L\b|накладн|waybill|коносамент|ТТН' },
  @{ code='svc_request'; rx='заявк|request|booking|заказ' }
)

Write-Host "Scanning $Root ..."
$allDirs = Get-ChildItem -LiteralPath $Root -Recurse -Directory -ErrorAction SilentlyContinue
$dealDirs = $allDirs | Where-Object { $_.Name -match $dateRx }
Write-Host "  $($allDirs.Count) directories, $($dealDirs.Count) date-named deal folders"

$deals = New-Object System.Collections.ArrayList
foreach ($d in $dealDirs) {
  $rel   = $d.FullName.Substring($Root.Length + 1)
  $parts = $rel -split '\\'
  if ($parts[$parts.Count-1] -notmatch $dateRx) { continue }
  $null = $parts[$parts.Count-1] -match $dateRx
  $day, $mon, $yr = $matches[1], $matches[2], $matches[3]
  try { $dealDate = [datetime]::ParseExact("$day.$mon.$yr", 'dd.MM.yyyy', $null) } catch { continue }

  $category = $parts[0]
  # nearest ancestor that is not noise / not a date  => the supplier
  $i = $parts.Count - 2
  while ($i -ge 1 -and ($parts[$i] -match $noiseRx -or $parts[$i] -match $dateRx)) { $i-- }
  if ($i -lt 1) { continue }
  $supplier = $parts[$i]

  # country: an explicit country level in the path wins, else infer from the name
  $country = ''
  foreach ($seg in $parts) { if ($countries.ContainsKey($seg)) { $country = $countries[$seg]; break } }
  if (-not $country) {
    foreach ($h in $nameCountry) { if ($supplier -match $h.rx) { $country = $h.c; break } }
  }

  $isService = ($category -eq 'Transportation')
  $rules = if ($isService) { $svcRules } else { $docRules }

  $files = Get-ChildItem -LiteralPath $d.FullName -Recurse -File -ErrorAction SilentlyContinue
  $found = @{}
  $refs  = New-Object System.Collections.ArrayList
  foreach ($f in $files) {
    foreach ($r in $rules) {
      if ($f.Name -match $r.rx) {
        if (-not $found.ContainsKey($r.code)) { $found[$r.code] = $f.Name }
        break
      }
    }
    # document reference numbers that appear in file names
    if ($f.BaseName -match '((UZ|GF|JNS|FSZY|PI|BAL)[A-Z0-9_\-\/]{4,})') {
      if ($refs -notcontains $matches[1]) { $null = $refs.Add($matches[1]) }
    }
  }

  $null = $deals.Add([ordered]@{
    category    = $category
    supplier    = $supplier
    country     = $country
    pipeline    = if ($isService) { 'service' } else { 'import' }
    deal_date   = $dealDate.ToString('yyyy-MM-dd')
    year        = [int]$yr
    rel_path    = $rel
    file_count  = $files.Count
    doc_types   = @($found.Keys | Sort-Object)
    doc_samples = $found
    refs        = @($refs | Select-Object -First 4)
  })
}

$payload = [ordered]@{
  scanned_at = (Get-Date).ToString('s')
  root       = $Root
  deals      = @($deals)
}
$payload | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $Out -Encoding utf8
Write-Host "Wrote $($deals.Count) deals -> $Out"
