# AgentSeed quick check - validate the plugin in the given directory.
# Usage:
#   .\check.ps1 [-Strict] [plugin-dir]
#   .\check.ps1 -SelfTest     # assert the bundled example fixtures behave
#
# Locates server/guard_cli.py by walking up from this script to a directory
# that ships it (repo root has it). Standalone installs fall back to the plugin
# home recorded in a `.agentseed-plugin-root` file next to SKILL.md (written by
# the installers), then to $env:USERPROFILE\.agentseed\AgentSeed. Override with
# AGENTSEED_PLUGIN_ROOT.
param(
    [switch]$Strict,
    [switch]$SelfTest,
    [string]$Target = "."
)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

function Test-Cli([string]$root) {
    return ($root) -and (Test-Path (Join-Path $root "server\guard_cli.py"))
}

$cli = $null
if (Test-Cli $env:AGENTSEED_PLUGIN_ROOT) {
    $cli = Join-Path $env:AGENTSEED_PLUGIN_ROOT "server\guard_cli.py"
}
if (-not $cli) {
    $d = $here
    foreach ($i in 1..6) {
        if (Test-Cli $d) { $cli = Join-Path $d "server\guard_cli.py"; break }
        $parent = Split-Path -Parent $d
        if (-not $parent -or $parent -eq $d) { break }
        $d = $parent
    }
}
if (-not $cli) {
    foreach ($pf in @((Join-Path $here "..\.agentseed-plugin-root"), (Join-Path $here ".agentseed-plugin-root"))) {
        if (Test-Path $pf) {
            $root = (Get-Content $pf -Raw).Trim()
            if (Test-Cli $root) { $cli = Join-Path $root "server\guard_cli.py"; break }
        }
    }
}
if (-not $cli) {
    $defaultRoot = Join-Path $env:USERPROFILE ".agentseed\AgentSeed"
    if (Test-Cli $defaultRoot) { $cli = Join-Path $defaultRoot "server\guard_cli.py" }
}

if (-not $cli) {
    Write-Error 'cannot locate server/guard_cli.py. Install the full AgentSeed plugin, set AGENTSEED_PLUGIN_ROOT, or clone it to %USERPROFILE%\.agentseed\AgentSeed.'
    exit 2
}
$pluginRoot = Split-Path -Parent (Split-Path -Parent $cli)

# --- interpreter probe: honour PYTHON, else the first candidate that ACTUALLY
# runs a trivial import. Get-Command is not enough: the Microsoft Store
# python3 stub is on PATH but exits non-zero, so we run "-c import sys". ---
function Test-Runnable([string]$cand) {
    if (-not $cand) { return $false }
    if (-not (Get-Command $cand -ErrorAction SilentlyContinue)) { return $false }
    & $cand -c "import sys" 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
}

$py = $null
if ($env:PYTHON) {
    if (-not (Test-Runnable $env:PYTHON)) {
        Write-Error "PYTHON=$($env:PYTHON) is set but cannot run (missing or a WindowsApps stub?)."
        exit 2
    }
    $py = $env:PYTHON
}
else {
    foreach ($cand in @("python", "py", "python3")) {
        if (Test-Runnable $cand) { $py = $cand; break }
    }
    if (-not $py) {
        Write-Error 'no working Python interpreter (tried python, py, python3). Set PYTHON.'
        exit 2
    }
}

if ($SelfTest) {
    $good = Join-Path $pluginRoot "examples\plugins\good-plugin"
    $broken = Join-Path $pluginRoot "examples\plugins\broken-plugin"
    $rc = 0

    $goodOut = & $py $cli check $good 2>&1
    if (($LASTEXITCODE -ne 0) -or (-not ($goodOut -match '"ok": true'))) {
        Write-Host "FAIL: good-plugin must report ok:true (exit 0)"
        $goodOut | ForEach-Object { Write-Host $_ }
        $rc = 1
    } else {
        Write-Host "PASS: good-plugin reports ok:true"
    }

    $brokenOut = & $py $cli check $broken 2>&1
    if (($LASTEXITCODE -eq 0) -or (-not ($brokenOut -match '"ok": false'))) {
        Write-Host "FAIL: broken-plugin must report errors (ok:false, exit != 0)"
        $brokenOut | ForEach-Object { Write-Host $_ }
        $rc = 1
    } else {
        Write-Host "PASS: broken-plugin fails as expected"
    }

    if ($rc -eq 0) { Write-Host "self-test: OK (interpreter=$py, plugin-root=$pluginRoot)" }
    exit $rc
}

if ($Strict) {
    & $py $cli check $Target
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $py $cli scan $Target --strict
    exit $LASTEXITCODE
}
else {
    & $py $cli check $Target
    exit $LASTEXITCODE
}
