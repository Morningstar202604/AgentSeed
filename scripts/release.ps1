# AgentSeed release wrapper — delegates to scripts/pack.py (zero-dep Python).
# Usage: .\release.ps1 [-CheckOnly]
param([switch]$CheckOnly)
$ErrorActionPreference = "Stop"
$py = if ($env:PYTHON) { $env:PYTHON } else { "python" }
$root = Split-Path -Parent $PSScriptRoot
$flag = if ($CheckOnly) { "--check-only" } else { "" }
& $py (Join-Path $PSScriptRoot "pack.py") $flag
exit $LASTEXITCODE
