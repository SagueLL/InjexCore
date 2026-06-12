[CmdletBinding()]
param()

$ErrorActionPreference = 'SilentlyContinue'

# ── USER CONFIG ───────────────────────────────────────────────────────────────
# Set to your Claude.ai plan:  'pro' | 'max5' | 'max20' | 'api'
# - pro   = Claude Pro   ($20/mo)
# - max5  = Claude Max   ($100/mo, 5x Pro)
# - max20 = Claude Max   ($200/mo, 20x Pro)
# - api   = Direct API   (pay-per-token; no monthly budget bar shown)
$Plan = 'max5'
# ─────────────────────────────────────────────────────────────────────────────

$raw = [Console]::In.ReadToEnd()
if ([string]::IsNullOrWhiteSpace($raw)) { return }

try { $ctx = $raw | ConvertFrom-Json } catch { return }

$transcriptPath = $ctx.transcript_path
$modelId        = if ($null -ne $ctx.model -and $null -ne $ctx.model.id)           { [string]$ctx.model.id           } else { '' }
$modelDisplay   = if ($null -ne $ctx.model -and $null -ne $ctx.model.display_name) { [string]$ctx.model.display_name } else { 'claude' }

# ── Model → context window ────────────────────────────────────────────────────
# All Claude 4.x / Fable 5 share a 200 k window; update here if a new model differs.
$ctxWindow = switch -Regex ($modelId) {
    'claude-3-5-sonnet|claude-3-opus|claude-3-haiku' { 200000 }
    default                                           { 200000 }
}

# ── Model → API pricing (USD / M tokens) ──────────────────────────────────────
$priceIn = 3.0; $priceOut = 15.0; $priceCacheR = 0.30; $priceCacheW = 3.75
switch -Regex ($modelId) {
    'opus' {
        $priceIn = 15.0; $priceOut = 75.0
        $priceCacheR = 1.50; $priceCacheW = 18.75
    }
    'haiku' {
        $priceIn = 0.80; $priceOut = 4.00
        $priceCacheR = 0.08; $priceCacheW = 1.00
    }
    # sonnet / fable / unknown → defaults (sonnet pricing)
}

# ── Parse transcript ──────────────────────────────────────────────────────────
$sumIn = 0L; $sumOut = 0L; $sumCacheR = 0L; $sumCacheW = 0L
$lastIn = 0;  $lastCacheR = 0;  $lastCacheW = 0;  $lastOut = 0
$lastSpeed   = 'standard'
$lastModel   = $modelId
$sessionMode = 'normal'
$lastHasThink = $false
$haveLast     = $false

if ($transcriptPath -and (Test-Path $transcriptPath)) {
    $lines = Get-Content -LiteralPath $transcriptPath
    foreach ($line in $lines) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        try { $entry = $line | ConvertFrom-Json } catch { continue }

        # Session mode entry (appears once at the top of a session)
        if ($entry.type -eq 'mode' -and $entry.mode) {
            $sessionMode = [string]$entry.mode
            continue
        }

        # Usage is in message.usage (assistant turns) or root usage (some entries)
        $u = $null
        if ($null -ne $entry.message -and $null -ne $entry.message.usage) { $u = $entry.message.usage }
        elseif ($null -ne $entry.usage) { $u = $entry.usage }
        if ($null -eq $u) { continue }

        $inTok  = if ($u.PSObject.Properties['input_tokens'])                { [long]$u.input_tokens }                else { 0L }
        $cacheR = if ($u.PSObject.Properties['cache_read_input_tokens'])     { [long]$u.cache_read_input_tokens }     else { 0L }
        $cacheC = if ($u.PSObject.Properties['cache_creation_input_tokens']) { [long]$u.cache_creation_input_tokens } else { 0L }
        $outTok = if ($u.PSObject.Properties['output_tokens'])               { [long]$u.output_tokens }               else { 0L }

        $sumIn     += $inTok
        $sumCacheR += $cacheR
        $sumCacheW += $cacheC
        $sumOut    += $outTok

        # Per-turn snapshot for context bar
        $lastIn = [int]$inTok; $lastCacheR = [int]$cacheR; $lastCacheW = [int]$cacheC; $lastOut = [int]$outTok
        $haveLast = $true

        # speed field ("standard" | "fast") surfaced by Claude Code
        if ($u.PSObject.Properties['speed']) { $lastSpeed = [string]$u.speed }

        # Model used for this specific turn (may differ from ctx if switched mid-session)
        if ($null -ne $entry.message -and $entry.message.PSObject.Properties['model']) {
            $lastModel = [string]$entry.message.model
        }

        # Detect extended thinking: any content block of type "thinking"
        $lastHasThink = $false
        if ($null -ne $entry.message -and $null -ne $entry.message.content) {
            foreach ($block in $entry.message.content) {
                if ($block.type -eq 'thinking') { $lastHasThink = $true; break }
            }
        }
    }
}

# ── Re-derive pricing from the model actually used in the last turn ────────────
if ($lastModel -ne $modelId -and -not [string]::IsNullOrEmpty($lastModel)) {
    switch -Regex ($lastModel) {
        'opus'  {
            $priceIn = 15.0; $priceOut = 75.0
            $priceCacheR = 1.50; $priceCacheW = 18.75
        }
        'haiku' {
            $priceIn = 0.80; $priceOut = 4.00
            $priceCacheR = 0.08; $priceCacheW = 1.00
        }
        default {
            $priceIn = 3.0; $priceOut = 15.0
            $priceCacheR = 0.30; $priceCacheW = 3.75
        }
    }
}

# ── Effort tag ────────────────────────────────────────────────────────────────
# Priority: thinking > fast > session mode > model family default
$effortTag = switch -Regex ($modelId) {
    'opus'   { 'high'  }
    'haiku'  { 'lite'  }
    default  { 'auto'  }
}
if ($sessionMode -eq 'fast' -or $lastSpeed -eq 'fast')  { $effortTag = 'fast'  }
if ($lastHasThink)                                       { $effortTag = 'think' }

# ── Context bar ────────────────────────────────────────────────────────────────
$ctxTokens = if ($haveLast) { $lastIn + $lastCacheR + $lastCacheW + $lastOut } else { 0 }
$ctxPct    = if ($ctxWindow -gt 0) { [math]::Min(100, [math]::Round(($ctxTokens / $ctxWindow) * 100, 1)) } else { 0 }

$cells  = 16
$filled = [int][math]::Min($cells, [math]::Max(0, [math]::Floor(($ctxPct / 100) * $cells)))
$bar    = ('#' * $filled) + ('-' * ($cells - $filled))

# ── Cost (API-equivalent USD) ─────────────────────────────────────────────────
$costRaw = (([double]$sumIn     / 1e6) * $priceIn)    +
           (([double]$sumOut    / 1e6) * $priceOut)   +
           (([double]$sumCacheR / 1e6) * $priceCacheR) +
           (([double]$sumCacheW / 1e6) * $priceCacheW)

# ── Plan budget indicator ──────────────────────────────────────────────────────
# Shows what fraction of the plan's monthly API-equivalent budget this session used.
$planMonthly = switch ($Plan) { 'pro' { 20.0 }; 'max5' { 100.0 }; 'max20' { 200.0 }; default { 0.0 } }

# ── ANSI colours ───────────────────────────────────────────────────────────────
$esc   = [char]27
$reset = "$esc[0m"
$dim   = "$esc[90m"
$cyan  = "$esc[36m"
$mag   = "$esc[35m"
$green = "$esc[32m"
$yel   = "$esc[33m"
$red   = "$esc[31m"
$white = "$esc[37m"

$ctxColor    = if ($ctxPct -lt 50) { $green } elseif ($ctxPct -lt 80) { $yel } else { $red }
$effortColor = switch ($effortTag) {
    'think' { $mag   }
    'fast'  { $cyan  }
    'high'  { $yel   }
    'lite'  { $dim   }
    default { $white }
}

# ── Helpers ────────────────────────────────────────────────────────────────────
function Format-Tokens([long]$n) {
    if ($n -ge 1000000) { return "$([math]::Round($n/1e6,2))M" }
    if ($n -ge 1000)    { return "$([math]::Round($n/1e3,1))k" }
    return [string]$n
}

# ── Build output ──────────────────────────────────────────────────────────────
$inv     = [System.Globalization.CultureInfo]::InvariantCulture
$costStr = '$' + $costRaw.ToString('N3', $inv)

$ctxStr  = Format-Tokens $ctxTokens
$winStr  = Format-Tokens $ctxWindow
$sessStr = Format-Tokens ($sumIn + $sumCacheR + $sumCacheW + $sumOut)
$outStr  = Format-Tokens $sumOut

# Segment 1: model + effort
$seg1 = "$dim[$modelDisplay]$reset ${effortColor}[$effortTag]$reset"

# Segment 2: context bar
$seg2 = "ctx ${ctxColor}[$bar]$reset $ctxStr/$winStr (${ctxPct}%)"

# Segment 3: session totals + cost
$seg3 = "session ${cyan}$sessStr$reset (out $outStr) $dim|$reset ${mag}${costStr}$reset"

# Segment 4: plan budget bar (skip for direct API)
$seg4 = ''
if ($planMonthly -gt 0) {
    $planPct   = [math]::Min(999, [math]::Round(($costRaw / $planMonthly) * 100, 3))
    $planColor = if ($planPct -lt 1.0) { $green } elseif ($planPct -lt 5.0) { $yel } else { $red }
    $planLabel = switch ($Plan) { 'pro' { 'Pro' }; 'max5' { 'Max5' }; 'max20' { 'Max20' }; default { 'Plan' } }
    $seg4 = "$dim|$reset $planColor${planLabel}:${planPct}%$reset"
}

"$seg1 $dim|$reset $seg2 $dim|$reset $seg3 $seg4"
