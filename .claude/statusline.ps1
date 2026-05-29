[CmdletBinding()]
param()

$ErrorActionPreference = 'SilentlyContinue'

$raw = [Console]::In.ReadToEnd()
if ([string]::IsNullOrWhiteSpace($raw)) { return }

try { $ctx = $raw | ConvertFrom-Json } catch { return }

$transcriptPath = $ctx.transcript_path
$modelName      = $ctx.model.display_name
$modelId        = $ctx.model.id

$ctxWindow = 200000

# Price per million tokens (USD). Defaults: Sonnet/Opus class.
# Opus 4.x pricing
$priceIn = 15.0; $priceOut = 75.0; $priceCacheR = 1.5; $priceCacheW = 18.75
if ($modelId -match 'sonnet') {
    $priceIn = 3.0; $priceOut = 15.0; $priceCacheR = 0.3; $priceCacheW = 3.75
} elseif ($modelId -match 'haiku') {
    $priceIn = 1.0; $priceOut = 5.0;  $priceCacheR = 0.1; $priceCacheW = 1.25
}

# Cumulative session counters
$sumIn = 0; $sumOut = 0; $sumCacheR = 0; $sumCacheW = 0
# Last-turn snapshot for the context bar
$lastIn = 0; $lastCacheR = 0; $lastCacheW = 0; $lastOut = 0
$haveLast = $false

if ($transcriptPath -and (Test-Path $transcriptPath)) {
    $lines = Get-Content -LiteralPath $transcriptPath
    for ($i = 0; $i -lt $lines.Count; $i++) {
        try { $entry = $lines[$i] | ConvertFrom-Json } catch { continue }

        $u = $entry.message.usage
        if ($null -eq $u) { $u = $entry.usage }
        if ($null -eq $u) { continue }

        $inTok  = 0; if ($u.input_tokens)                { $inTok  = [int]$u.input_tokens }
        $cacheR = 0; if ($u.cache_read_input_tokens)     { $cacheR = [int]$u.cache_read_input_tokens }
        $cacheC = 0; if ($u.cache_creation_input_tokens) { $cacheC = [int]$u.cache_creation_input_tokens }
        $outTok = 0; if ($u.output_tokens)               { $outTok = [int]$u.output_tokens }

        $sumIn     += $inTok
        $sumCacheR += $cacheR
        $sumCacheW += $cacheC
        $sumOut    += $outTok

        $lastIn = $inTok; $lastCacheR = $cacheR; $lastCacheW = $cacheC; $lastOut = $outTok
        $haveLast = $true
    }
}

# Context = tokens loaded into the *current* turn (everything the model just saw + emitted)
$ctxTokens = 0
if ($haveLast) { $ctxTokens = $lastIn + $lastCacheR + $lastCacheW + $lastOut }

$ctxPct = 0
if ($ctxWindow -gt 0) {
    $ctxPct = [math]::Round(($ctxTokens / $ctxWindow) * 100, 1)
    if ($ctxPct -gt 100) { $ctxPct = 100 }
}

$cells  = 16
$filled = [int][math]::Floor(($ctxPct / 100) * $cells)
if ($filled -lt 0)      { $filled = 0 }
if ($filled -gt $cells) { $filled = $cells }
$empty  = $cells - $filled
$bar    = ('#' * $filled) + ('-' * $empty)

$esc = [char]27
if     ($ctxPct -lt 50) { $ctxColor = "$esc[32m" }
elseif ($ctxPct -lt 80) { $ctxColor = "$esc[33m" }
else                    { $ctxColor = "$esc[31m" }
$dim   = "$esc[90m"
$cyan  = "$esc[36m"
$mag   = "$esc[35m"
$reset = "$esc[0m"

function Format-Tokens($n) {
    if ($n -ge 1000000) {
        $m = [math]::Round($n / 1000000.0, 2)
        return "${m}M"
    }
    if ($n -ge 1000) {
        $k = [math]::Round($n / 1000.0, 1)
        return "${k}k"
    }
    return [string]$n
}

# Session totals (what the user actually "spent")
$sessionTotal = $sumIn + $sumCacheR + $sumCacheW + $sumOut

# Estimated cost
$cost = (($sumIn      / 1000000.0) * $priceIn)      `
      + (($sumOut     / 1000000.0) * $priceOut)     `
      + (($sumCacheR  / 1000000.0) * $priceCacheR)  `
      + (($sumCacheW  / 1000000.0) * $priceCacheW)

$inv = [System.Globalization.CultureInfo]::InvariantCulture
$costStr = '$' + $cost.ToString('N2', $inv)

$ctxStr  = Format-Tokens $ctxTokens
$winStr  = Format-Tokens $ctxWindow
$sessStr = Format-Tokens $sessionTotal
$outStr  = Format-Tokens $sumOut

$modelTag = 'claude'
if ($modelName) { $modelTag = $modelName }

"$dim[$modelTag]$reset ctx $ctxColor[$bar]$reset $ctxStr/$winStr ($ctxPct%) $dim|$reset session $cyan$sessStr$reset (out $outStr) $dim|$reset $mag$costStr$reset"
