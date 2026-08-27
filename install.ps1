# AgentSeed installer - download the latest release and wire it into a client.
#
# Usage: .\install.ps1 [-Client auto|claude|opencode|cursor|manual] [-Dir TARGET]
#                      [-Sha256 HEX] [-Url ZIP_URL] [-Repo owner/name]
#                      [-Forge github|gitcode] [-Hooks]
#
# -Url   : download a specific release zip directly (any host). Skips repo
#          resolution entirely.
# -Repo  : override the repository (default: Morningstar202604/agentseed-mcp,
#          the canonical GitHub home; gitee/gitcode mirrors live under
#          badhope/agentseed-mcp).
# -Forge : which release API to query (default: github). Use `gitcode` only
#          for the CN mirror - its release API does NOT order newest-first, so
#          the newest tag is resolved from /tags and sorted by version.
# -Hooks : additionally register the client-enforcement hook (Claude Code:
#          merges into ~\.claude\settings.json, idempotent; the previous config
#          is kept as settings.json.bak).
param(
    [ValidateSet("auto", "claude", "opencode", "cursor", "manual")]
    [string]$Client = "auto",
    [string]$Dir = "",
    [string]$Sha256 = "",
    [string]$Url = "",
    [ValidateSet("github", "gitcode")]
    [string]$Forge = "github",
    [string]$Repo = "Morningstar202604/agentseed-mcp",
    [switch]$Hooks
)
$ErrorActionPreference = "Stop"
# NOTE: PowerShell variables are case-insensitive, so this must NOT be named
# `$repo` - that silently shadows the `-Repo` parameter and every caller
# override would be discarded (the bug this comment exists to prevent).
$targetRepo = $Repo

function Resolve-LatestUrl {
    if ($Url) { return $Url }
    if ($Forge -eq "gitcode") {
        Write-Host "==> resolving newest release of $targetRepo on GitCode"
        # GitCode/Gitee return releases oldest-first and /releases/latest 400s
        # when empty: take the highest version tag first, then its release.
        $tags = Invoke-RestMethod -Uri "https://api.gitcode.com/api/v5/repos/$targetRepo/tags?per_page=100" `
                -Headers @{ "User-Agent" = "agentseed-installer" }
        $newest = @($tags | ForEach-Object { $_.name } | Where-Object { $_ -match '^v\d+(\.\d+)*$' } |
            Sort-Object { [version]($_.TrimStart('v')) } -Descending | Select-Object -First 1)
        if (-not $newest) { throw "no version tags on $targetRepo" }
        Write-Host "==> newest mirror tag: $newest"
        $rel = Invoke-RestMethod -Uri "https://api.gitcode.com/api/v5/repos/$targetRepo/releases/tags/$newest" `
                -Headers @{ "User-Agent" = "agentseed-installer" }
        $asset = @($rel.assets) | Where-Object { $_.name -like "*.zip" } | Select-Object -First 1
        if (-not $asset) { throw "no .zip asset on $targetRepo release $newest" }
        return $asset.browser_download_url
    }
    Write-Host "==> resolving latest release of $targetRepo"
    $rel = Invoke-RestMethod -Uri "https://api.github.com/repos/$targetRepo/releases/latest" `
            -Headers @{ "User-Agent" = "agentseed-installer" }
    $asset = @($rel.assets) | Where-Object { $_.name -like "*.zip" } | Select-Object -First 1
    if (-not $asset) { throw "no .zip asset on the latest $targetRepo release" }
    return $asset.browser_download_url
}

# `python3` on Windows is usually the Microsoft Store stub (exits 9009), so
# probe what actually works instead of trusting one alias.
function Resolve-Interpreter {
    $candidates = if ($env:PYTHON) { @($env:PYTHON) } else { @("python", "py", "python3") }
    foreach ($cand in $candidates) {
        try {
            $null = & $cand -c "import sys" 2>$null
            if ($LASTEXITCODE -eq 0) { return $cand }
        } catch { }
    }
    return $null
}

function Backup-Aside([string]$path) {
    if (-not (Test-Path $path)) { return }
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $bak = "$path.bak-$stamp"
    Move-Item -Path $path -Destination $bak
    Write-Host "==> previous copy moved aside: $bak"
}

function Patch-McpJson([string]$installDir) {
    # mcp.json can only carry one literal interpreter token (the Agent Plugins
    # 1.0.0 schema forbids paths in `command`), so fix it up for this platform.
    # Edit the raw text: re-serialising with ConvertTo-Json + Set-Content
    # -Encoding UTF8 would add a BOM under Windows PowerShell 5.1 and turn the
    # manifest into invalid JSON.
    $mcpJson = Join-Path $installDir "mcp.json"
    if (-not (Test-Path $mcpJson)) { return }
    $raw = [System.IO.File]::ReadAllText($mcpJson)
    $patched = $raw -replace '("command"\s*:\s*)"python3"', '$1"python"'
    if ($patched -eq $raw) { return }
    try { $null = $patched | ConvertFrom-Json } catch {
        Write-Warning "refusing to rewrite ${mcpJson}: result would not parse as JSON"
        return
    }
    [System.IO.File]::WriteAllText($mcpJson, $patched, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "==> $mcpJson : 'command' rewritten python3 -> python (Windows)"
}

$downloadUrl = Resolve-LatestUrl

$tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("agentseed-" + [guid]::NewGuid())
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
try {
    Write-Host "==> downloading $downloadUrl"
    Invoke-WebRequest -Uri $downloadUrl -OutFile "$tmp\agentseed.zip" `
        -Headers @{ "User-Agent" = "agentseed-installer" }
    # Verify BEFORE extracting: an unverified archive must never touch the disk
    # as loose files (install.sh has always done it in this order).
    if ($Sha256) {
        $got = (Get-FileHash -Algorithm SHA256 "$tmp\agentseed.zip").Hash.ToLower()
        if ($got -ne $Sha256.ToLower()) {
            throw "checksum mismatch: expected $Sha256, got $got"
        }
        Write-Host "==> checksum verified"
    } else {
        Write-Warning "no -Sha256 given; the archive is NOT integrity-checked. Pin a release checksum to protect against tampering."
    }
    Expand-Archive "$tmp\agentseed.zip" "$tmp\x" -Force
    $src = Get-ChildItem "$tmp\x" -Recurse -Filter plugin.json |
        Select-Object -First 1 | ForEach-Object { $_.Directory.FullName }
    if (-not $src) { throw "plugin.json not found in archive" }

    $py = Resolve-Interpreter
    if (-not $py) {
        throw "no usable Python interpreter (tried python, py, python3) - set `$env:PYTHON='C:\path\to\python.exe'"
    }
    Write-Host "==> interpreter detected for this machine: $py"

    # 1) stable full-plugin home (the MCP server runs from here)
    $base = if ($env:AGENTSEED_HOME) { $env:AGENTSEED_HOME } else { Join-Path $HOME ".agentseed" }
    $pluginHome = Join-Path $base "AgentSeed"
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $pluginHome) | Out-Null
    Backup-Aside $pluginHome
    Copy-Item -Recurse $src $pluginHome
    Write-Host "==> full plugin installed to $pluginHome"

    # mcp.json can only carry one literal interpreter token (the Agent Plugins
    # 1.0.0 schema forbids paths in `command`), so fix it up for this platform.
    Patch-McpJson $pluginHome

    # 2) flat skill copy so clients that scan <dir>\SKILL.md find it
    $skillSrc = Join-Path $pluginHome "skills\verify-before-code"
    function Install-Skill([string]$dest) {
        Backup-Aside $dest
        New-Item -ItemType Directory -Force -Path $dest | Out-Null
        Copy-Item -Recurse (Join-Path $skillSrc "*") $dest
        Set-Content -Path (Join-Path $dest ".agentseed-plugin-root") -Value $pluginHome -NoNewline
        Write-Host "==> skill installed to $dest"
    }
    $serverPy = Join-Path $pluginHome "server\guard_server.py"
    $hookPy = Join-Path $pluginHome "server\guard_hook.py"

    switch ($Client) {
        "claude" {
            Install-Skill "$HOME\.claude\skills\verify-before-code"
            if ($Hooks) {
                & $py $hookPy register --client claude
                if ($LASTEXITCODE -ne 0) {
                    Write-Warning "hook registration failed; run: $py `"$hookPy`" register --client claude"
                }
            }
            Write-Host ""
            Write-Host "==> final step - register the MCP server:"
            Write-Host "    claude mcp add agentseed -- $py `"$serverPy`""
        }
        "opencode" {
            Install-Skill "$HOME\.config\opencode\skill\verify-before-code"
            if ($Hooks) { & $py $hookPy register --client opencode }
            Write-Host ""
            Write-Host "==> final step - add to ~/.config/opencode/opencode.json:"
            Write-Host "    `"mcp`": { `"agentseed`": { `"type`": `"local`","
            Write-Host "        `"command`": [`"$py`", `"$serverPy`"], `"enabled`": true } }"
        }
        "cursor" {
            if ($Hooks) { & $py $hookPy register --client cursor }
            Write-Host "==> Cursor has no stable Agent Plugins directory yet."
            Write-Host "    Plugin kept at: $pluginHome"
            Write-Host "    Register the MCP server in Cursor settings:"
            Write-Host "      command: $py  args: [$serverPy]"
        }
        default {
            $dest = if ($Dir) { Join-Path $Dir "AgentSeed" } else { Join-Path $PWD "AgentSeed" }
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dest) | Out-Null
            Backup-Aside $dest
            Copy-Item -Recurse $src $dest
            Patch-McpJson $dest
            Write-Host "==> plugin copied to $dest"
            Write-Host "==> mcp.json in that copy now uses command=`"python`" for this machine;"
            Write-Host "    on macOS/Linux use `"python3`", or run: npx agentseed-mcp."
            Write-Host "==> done. Drop it into your client, or re-run with -Client claude|opencode."
        }
    }
}
finally {
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}
