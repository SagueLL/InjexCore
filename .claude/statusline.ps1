[CmdletBinding()]
param()

$ErrorActionPreference = 'SilentlyContinue'

# ── USER CONFIG ───────────────────────────────────────────────────────────────
# Token budgets are expressed in OUTPUT tokens (the tokens you generate).
#
#   $WeeklyBudget  — the number treated as 100%. Claude does NOT store your real
#                    plan limit in any local file (the /usage figure is fetched
#                    live from Anthropic's servers), so this is a fixed reference
#                    you control. 1,000,000 ≈ the "1M" figure; tweak freely.
#   $BarScale      — what the session bar's 100% equals. Defaults to the weekly
#                    budget, so one session usually fills only a sliver. Lower it
#                    (e.g. 200000) if you want the bar to move more per session.
#   $WeekWindowDays— rolling window for the "wk" figure. Anthropic's exact weekly
#                    reset isn't knowable locally, so a 7-day rolling window is
#                    used as an honest approximation.
$WeeklyBudget   = 1000000
$BarScale       = $WeeklyBudget
$WeekWindowDays = 7

# Where every project's session transcripts live. The "wk" total is aggregated
# across ALL of them (account-wide), which is why it survives closing a terminal.
$ProjectsRoot   = Join-Path $env:USERPROFILE '.claude\projects'

# Tiny cache so the account-wide weekly scan doesn't re-parse on every render.
$CachePath      = Join-Path $env:USERPROFILE '.claude\statusline_usage_cache.json'
$CacheTtlSec    = 8
# ─────────────────────────────────────────────────────────────────────────────

$raw = [Console]::In.ReadToEnd()
if ([string]::IsNullOrWhiteSpace($raw)) { return }

try { $ctx = $raw | ConvertFrom-Json } catch { return }

$transcriptPath = $ctx.transcript_path
$modelId      = if ($null -ne $ctx.model -and $null -ne $ctx.model.id)           { [string]$ctx.model.id           } else { '' }
$modelDisplay = if ($null -ne $ctx.model -and $null -ne $ctx.model.display_name) { [string]$ctx.model.display_name } else { 'claude' }

# ── Helpers ────────────────────────────────────────────────────────────────────
$utcStyles = [System.Globalization.DateTimeStyles]::AdjustToUniversal -bor `
             [System.Globalization.DateTimeStyles]::AssumeUniversal
$invariant = [System.Globalization.CultureInfo]::InvariantCulture

function Read-UsageLine {
    # Parses one transcript JSONL line. Returns $null unless it carries a usage
    # block. Anchors at "usage":{ so the model's own prose (which may contain the
    # literal "output_tokens") can never be mistaken for the real counter.
    param([string]$Line)

    $ui = $Line.IndexOf('"usage":{')
    if ($ui -lt 0) { return $null }
    $tail = $Line.Substring($ui)

    $oM = [regex]::Match($tail, '"output_tokens":(\d+)')
    if (-not $oM.Success) { return $null }

    $tsUtc = $null
    $tM = [regex]::Match($tail, '"timestamp":"([^"]+)"')   # top-level ts sits after usage
    if ($tM.Success) {
        $parsed = [datetime]::MinValue
        if ([datetime]::TryParse($tM.Groups[1].Value, $invariant, $utcStyles, [ref]$parsed)) {
            $tsUtc = $parsed
        }
    }

    $speed = ''
    $sM = [regex]::Match($tail, '"speed":"([a-z]+)"')
    if ($sM.Success) { $speed = $sM.Groups[1].Value }

    $model = ''
    $mM = [regex]::Match($Line, '"model":"(claude[^"]+)"')
    if ($mM.Success) { $model = $mM.Groups[1].Value }

    return @{
        Out          = [long]$oM.Groups[1].Value
        TimestampUtc = $tsUtc
        Speed        = $speed
        Model        = $model
        HasThink     = ($Line.IndexOf('"type":"thinking"') -ge 0)
    }
}

function Format-Tokens {
    param([long]$n)
    if ($n -ge 1000000) { return ('{0}M' -f [math]::Round($n / 1e6, 2)) }
    if ($n -ge 1000)    { return ('{0}k' -f [math]::Round($n / 1e3, 1)) }
    return [string]$n
}

function New-Bar {
    param([double]$pct, [int]$cells)
    $filled = [int][math]::Min($cells, [math]::Max(0, [math]::Floor(($pct / 100.0) * $cells)))
    return ('#' * $filled) + ('-' * ($cells - $filled))
}

# ── Session output (the bar) — current transcript only, every render ───────────
$sessionOut = 0L
$lastSpeed  = ''
$lastThink  = $false
$lastModel  = $modelId

if ($transcriptPath -and (Test-Path -LiteralPath $transcriptPath)) {
    try {
        foreach ($line in [System.IO.File]::ReadLines($transcriptPath)) {
            if ($line.IndexOf('"usage":{') -lt 0) { continue }
            $u = Read-UsageLine $line
            if ($null -eq $u) { continue }
            $sessionOut += $u.Out
            if ($u.Speed) { $lastSpeed = $u.Speed }
            if ($u.Model) { $lastModel = $u.Model }
            $lastThink = $u.HasThink
        }
    } catch { }
}

# ── Weekly output (persistent) — all projects, rolling window, cached ──────────
$nowUtc    = (Get-Date).ToUniversalTime()
$cutoffUtc = $nowUtc.AddDays(-$WeekWindowDays)
$weeklyOut = $null

try {
    if (Test-Path -LiteralPath $CachePath) {
        $c = Get-Content -LiteralPath $CachePath -Raw | ConvertFrom-Json
        $cachedAt = [datetime]::MinValue
        if ([datetime]::TryParse([string]$c.computedAtUtc, $invariant, $utcStyles, [ref]$cachedAt)) {
            $age = ($nowUtc - $cachedAt).TotalSeconds
            if ($age -ge 0 -and $age -lt $CacheTtlSec -and [int]$c.windowDays -eq $WeekWindowDays) {
                $weeklyOut = [long]$c.weeklyOut
            }
        }
    }
} catch { }

if ($null -eq $weeklyOut) {
    $weeklyOut = 0L
    if (Test-Path -LiteralPath $ProjectsRoot) {
        try {
            $files = Get-ChildItem -LiteralPath $ProjectsRoot -Recurse -Filter *.jsonl -File -ErrorAction SilentlyContinue |
                     Where-Object { $_.LastWriteTimeUtc -ge $cutoffUtc }
            foreach ($f in $files) {
                try {
                    foreach ($line in [System.IO.File]::ReadLines($f.FullName)) {
                        if ($line.IndexOf('"usage":{') -lt 0) { continue }
                        $u = Read-UsageLine $line
                        if ($null -eq $u) { continue }
                        if ($null -ne $u.TimestampUtc -and $u.TimestampUtc -lt $cutoffUtc) { continue }
                        $weeklyOut += $u.Out
                    }
                } catch { }
            }
        } catch { }
    }
    try {
        @{
            computedAtUtc = $nowUtc.ToString('o')
            weeklyOut     = $weeklyOut
            windowDays    = $WeekWindowDays
        } | ConvertTo-Json -Compress | Set-Content -LiteralPath $CachePath -Encoding UTF8
    } catch { }
}

# ── Effort tag (thinking > fast > model-family default) ────────────────────────
$effortTag = 'auto'
switch -Regex ($modelId) {
    'opus'  { $effortTag = 'high' }
    'haiku' { $effortTag = 'lite' }
}
if ($lastSpeed -eq 'fast') { $effortTag = 'fast' }
if ($lastThink)            { $effortTag = 'think' }

# ── Percentages ────────────────────────────────────────────────────────────────
$sessPct = if ($BarScale -gt 0)     { [math]::Min(100, [math]::Round(($sessionOut / [double]$BarScale) * 100, 1)) } else { 0 }
$wkPct   = if ($WeeklyBudget -gt 0) {                   [math]::Round(($weeklyOut  / [double]$WeeklyBudget) * 100, 1) } else { 0 }

$cells = 14
$bar   = New-Bar $sessPct $cells

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

$barColor = if ($sessPct -lt 50) { $green } elseif ($sessPct -lt 80) { $yel } else { $red }
$wkColor  = if ($wkPct  -lt 50)  { $green } elseif ($wkPct  -lt 80)  { $yel } else { $red }
$effortColor = switch ($effortTag) {
    'think' { $mag   }
    'fast'  { $cyan  }
    'high'  { $yel   }
    'lite'  { $dim   }
    default { $white }
}

# ── Build output ──────────────────────────────────────────────────────────────
$budgetStr = Format-Tokens $BarScale
$sessStr   = Format-Tokens $sessionOut
$weekStr   = Format-Tokens $weeklyOut

# Segment 1: model + effort
$seg1 = "$dim[$modelDisplay]$reset ${effortColor}[$effortTag]$reset"

# Segment 2: this session's output tokens (the bar), scaled to the budget
$seg2 = "out ${barColor}[$bar]$reset $sessStr/$budgetStr (${sessPct}%)"

# Segment 3: rolling-window output across every session — persists across terminals
$seg3 = "wk ${wkColor}$weekStr/$budgetStr$reset (${wkPct}%)"

"$seg1 $dim|$reset $seg2 $dim|$reset $seg3"
