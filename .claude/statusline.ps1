[CmdletBinding()]
param()

$ErrorActionPreference = 'SilentlyContinue'

# ── USER CONFIG ───────────────────────────────────────────────────────────────
# Token budgets are expressed in OUTPUT tokens (the tokens you generate).
#
#   $WeeklyBudget  — the number treated as 100%. Claude does NOT store your real
#                    plan limit in any local file (the /usage figure is fetched
#                    live from Anthropic's servers), so this is a fixed reference
#                    you control. 10000,000 ≈ the "10M" figure aprox; tweak freely.
#   $BarScale      — what the session bar's 100% equals. Defaults to the weekly
#                    budget, so one session usually fills only a sliver. Lower it
#                    (e.g. 200000) if you want the bar to move more per session.
#   $WeekWindowDays— rolling window for the "wk" figure. Anthropic's exact weekly
#                    reset isn't knowable locally, so a 7-day rolling window is
#                    used as an honest approximation.
$WeeklyBudget   = 10000000
$BarScale       = 1000000
$WeekWindowDays = 7

# Where every project's session transcripts live. The "wk" total is aggregated
# across ALL of them (account-wide), which is why it survives closing a terminal.
$ProjectsRoot   = Join-Path $env:USERPROFILE '.claude\projects'

# Cache so the account-wide weekly scan stays cheap: a short TTL fast-path plus a
# per-file sum (keyed by mtime+size) so only changed transcripts are re-parsed.
$CachePath      = Join-Path $env:USERPROFILE '.claude\statusline_usage_cache.json'
$CacheTtlSec    = 15
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

    return @{
        Out          = [long]$oM.Groups[1].Value
        TimestampUtc = $tsUtc
        Speed        = $speed
        HasThink     = ($Line.IndexOf('"type":"thinking"') -ge 0)
    }
}

function Format-Tokens {
    # Always invariant (period decimal) so locale never turns 1.5M into "1,5M".
    param([long]$n)
    $ic = [System.Globalization.CultureInfo]::InvariantCulture
    if ($n -ge 1000000) { return ([math]::Round($n / 1e6, 2)).ToString($ic) + 'M' }
    if ($n -ge 1000)    { return ([math]::Round($n / 1e3, 1)).ToString($ic) + 'k' }
    return [string]$n
}

function New-Bar {
    param([double]$pct, [int]$cells)
    $filled = [int][math]::Min($cells, [math]::Max(0, [math]::Floor(($pct / 100.0) * $cells)))
    return ('#' * $filled) + ('-' * ($cells - $filled))
}

function Measure-WeeklyOutput {
    # Sums OUTPUT tokens across every project transcript whose lines fall inside
    # the rolling window. Incremental: a file that is unchanged (same mtime+size)
    # AND fully inside the window contributes its cached sum without re-reading,
    # so steady-state only the active session file is actually parsed.
    param([string]$ProjectsRoot, [datetime]$CutoffUtc, $CachedFiles)

    $total    = 0L
    $newFiles = @{}
    if (-not (Test-Path -LiteralPath $ProjectsRoot)) {
        return @{ Total = $total; Files = $newFiles }
    }

    $cutTicks = $CutoffUtc.Ticks
    $files = Get-ChildItem -LiteralPath $ProjectsRoot -Recurse -Filter *.jsonl -File -ErrorAction SilentlyContinue |
             Where-Object { $_.LastWriteTimeUtc -ge $CutoffUtc }

    foreach ($f in $files) {
        $key        = $f.FullName
        $mtimeTicks = $f.LastWriteTimeUtc.Ticks
        $len        = [long]$f.Length

        $entry = $null
        if ($null -ne $CachedFiles -and $CachedFiles.PSObject.Properties[$key]) { $entry = $CachedFiles.$key }

        if ($null -ne $entry -and [long]$entry.mtimeTicks -eq $mtimeTicks -and
            [long]$entry.length -eq $len -and [long]$entry.minTsTicks -ge $cutTicks) {
            # Unchanged and fully inside the window → reuse cached sum verbatim.
            $total += [long]$entry.out
            $newFiles[$key] = @{ mtimeTicks = $mtimeTicks; length = $len; out = [long]$entry.out
                                 minTsTicks = [long]$entry.minTsTicks; maxTsTicks = [long]$entry.maxTsTicks }
            continue
        }

        # New, changed, or straddling the cutoff → parse it.
        $sumAll = 0L; $sumWin = 0L
        $minTicks = [long]::MaxValue; $maxTicks = [long]::MinValue
        try {
            foreach ($line in [System.IO.File]::ReadLines($key)) {
                if ($line.IndexOf('"usage":{') -lt 0) { continue }
                $u = Read-UsageLine $line
                if ($null -eq $u) { continue }
                $sumAll += $u.Out
                if ($null -ne $u.TimestampUtc) {
                    $tt = $u.TimestampUtc.Ticks
                    if ($tt -lt $minTicks) { $minTicks = $tt }
                    if ($tt -gt $maxTicks) { $maxTicks = $tt }
                    if ($tt -ge $cutTicks) { $sumWin += $u.Out }
                } else {
                    $sumWin += $u.Out   # no parseable timestamp: file is in-window by mtime, count it
                }
            }
        } catch { }
        if ($minTicks -eq [long]::MaxValue) { $minTicks = $cutTicks }
        if ($maxTicks -eq [long]::MinValue) { $maxTicks = $mtimeTicks }

        $total += $sumWin
        $newFiles[$key] = @{ mtimeTicks = $mtimeTicks; length = $len; out = $sumAll
                             minTsTicks = $minTicks; maxTsTicks = $maxTicks }
    }

    return @{ Total = $total; Files = $newFiles }
}

# ── Session output (the bar) — current transcript only, every render ───────────
$sessionOut = 0L
$lastSpeed  = ''
$lastThink  = $false

if ($transcriptPath -and (Test-Path -LiteralPath $transcriptPath)) {
    try {
        foreach ($line in [System.IO.File]::ReadLines($transcriptPath)) {
            if ($line.IndexOf('"usage":{') -lt 0) { continue }
            $u = Read-UsageLine $line
            if ($null -eq $u) { continue }
            $sessionOut += $u.Out
            if ($u.Speed) { $lastSpeed = $u.Speed }
            $lastThink = $u.HasThink
        }
    } catch { }
}

# ── Weekly output (persistent) — all projects, rolling window, cached ──────────
$nowUtc    = (Get-Date).ToUniversalTime()
$cutoffUtc = $nowUtc.AddDays(-$WeekWindowDays)

$cache = $null
try {
    if (Test-Path -LiteralPath $CachePath) {
        $cache = Get-Content -LiteralPath $CachePath -Raw | ConvertFrom-Json
    }
} catch { }

# Fast path: a fresh cache (within TTL, same window) is returned verbatim.
$weeklyOut = $null
if ($null -ne $cache) {
    $cachedAt = [datetime]::MinValue
    if ([int]$cache.windowDays -eq $WeekWindowDays -and
        [datetime]::TryParse([string]$cache.computedAtUtc, $invariant, $utcStyles, [ref]$cachedAt)) {
        $age = ($nowUtc - $cachedAt).TotalSeconds
        if ($age -ge 0 -and $age -lt $CacheTtlSec) { $weeklyOut = [long]$cache.weeklyOut }
    }
}

# Slow path: re-aggregate, but reuse per-file sums for unchanged transcripts.
if ($null -eq $weeklyOut) {
    $cachedFiles = if ($null -ne $cache) { $cache.files } else { $null }
    $res = Measure-WeeklyOutput -ProjectsRoot $ProjectsRoot -CutoffUtc $cutoffUtc -CachedFiles $cachedFiles
    $weeklyOut = [long]$res.Total
    try {
        @{
            computedAtUtc = $nowUtc.ToString('o')
            windowDays    = $WeekWindowDays
            weeklyOut     = $weeklyOut
            files         = $res.Files
        } | ConvertTo-Json -Depth 6 -Compress | Set-Content -LiteralPath $CachePath -Encoding UTF8
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
$budgetStr  = Format-Tokens $BarScale
$sessStr    = Format-Tokens $sessionOut
$weekStr    = Format-Tokens $weeklyOut
$sessPctStr = $sessPct.ToString($invariant)
$wkPctStr   = $wkPct.ToString($invariant)
$wkBudgetStr  = "10M"  # hard-coded for now, since the weekly budget is user-configurable and not fetched from Anthropic

# Segment 1: model + effort
$seg1 = "$dim[$modelDisplay]$reset ${effortColor}[$effortTag]$reset"

# Segment 2: this session's output tokens (the bar), scaled to the budget
$seg2 = "out ${barColor}[$bar]$reset $sessStr/$budgetStr (${sessPctStr}%)"

# Segment 3: rolling-window output across every session — persists across terminals
$seg3 = "wk ${wkColor}$weekStr/$wkBudgetStr$reset (${wkPctStr}%)"

"$seg1 $dim|$reset $seg2 $dim|$reset $seg3"
