# AgentSeed installer - download the latest release and wire it into a client.
#
# Usage: .\install.ps1 [-Client claude|opencode|cursor|manual] [-Dir TARGET]
#                      [-Sha256 HEX] [-Url ZIP_URL] [-Repo owner/name]
#                      [-Forge github|gitcode] [-Hooks]
#
# -Url   : download a specific release zip directly (any host). Skips repo
#          resolution entirely.
# -Repo  : override the repository (default: badhope/AgentSeed, the canonical
#          GitCode home; weed33834/* on GitHub is a deprecated mirror).
# -Forge : which release API to query (default: gitcode).
# -Hooks : additionally register the client-enforcement hook (Claude Code:
#          merges into ~\.claude\settings.json, idempotent).
param(
    [ValidateSet("auto", "claude", "opencode", "cursor", "manual")]
    [string]$Client = "auto",
    [string]$Dir = "",
    [string]$Sha256 = "",
    [string]$Url = "",
    [ValidateSet("github", "gitcode")]
    [string]$Forge = "gitcode",
    [string]$Repo = "badhope/AgentSeed",
    [switch]$Hooks
)
$ErrorActionPreference = "Stop"
$repo = "badhope/AgentSeed"

if ($Url) {
    $downloadUrl = $Url
} elseif ($Forge -eq "gitcode") {
    Write-Host "==> resolving latest GitCode release of $Repo"
    # GitCode v5 API (Gitee-compatible); /releases/latest 400s when empty.
    $rel = Invoke-RestMethod -Uri "https://api.gitcode.com/api/v5/repos/$Repo/releases?per_page=1" `
            -Headers @{ "User-Agent" = "agentseed-installer" }
    $asset = @($rel)[0].assets | Where-Object { $_.name -like "*.zip" } | Select-Object -First 1
    if (-not $asset) { throw "no .zip asset on the latest GitCode release" }
    $downloadUrl = $asset.browser_download_url
} else {
    Write-Host "==> resolving latest release of $Repo"
    $rel = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/latest" `
            -Headers @{ "User-Agent" = "agentseed-installer" }
    $asset = $rel.assets | Where-Object { $_.name -like "*.zip" } | Select-Object -First 1
    if (-not $asset) { throw "no .zip asset on the latest release" }
    $downloadUrl = $asset.browser_download_url
}

$tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("agentseed-" + [guid]::NewGuid())
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
try {
    Write-Host "==> downloading $downloadUrl"
    Invoke-WebRequest -Uri $downloadUrl -OutFile "$tmp\agentseed.zip" `
        -Headers @{ "User-Agent" = "agentseed-installer" }
    Expand-Archive "$tmp\agentseed.zip" "$tmp\x" -Force
    if ($Sha256) {
        $got = (Get-FileHash -Algorithm SHA256 "$tmp\agentseed.zip").Hash.ToLower()
        if ($got -ne $Sha256.ToLower()) {
            throw "checksum mismatch: expected $Sha256, got $got"
        }
        Write-Host "==> checksum verified"
    } else {
        Write-Warning "no -Sha256 given; the archive is NOT integrity-checked. Pin a release checksum to protect against tampering."
    }
    $src = Get-ChildItem "$tmp\x" -Recurse -Filter plugin.json |
        Select-Object -First 1 | ForEach-Object { $_.Directory.FullName }
    if (-not $src) { throw "plugin.json not found in archive" }

    # 1) stable full-plugin home (the MCP server runs from here)
    $base = if ($env:AGENTSEED_HOME) { $env:AGENTSEED_HOME } else { Join-Path $HOME ".agentseed" }
    $pluginHome = Join-Path $base "AgentSeed"
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $pluginHome) | Out-Null
    if (Test-Path $pluginHome) { Remove-Item -Recurse -Force $pluginHome }
    Copy-Item -Recurse $src $pluginHome
    Write-Host "==> full plugin installed to $pluginHome"

    # 2) flat skill copy so clients that scan <dir>\SKILL.md find it
    $skillSrc = Join-Path $pluginHome "skills\verify-before-code"
    function Install-Skill([string]$dest) {
        if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
        New-Item -ItemType Directory -Force -Path $dest | Out-Null
        Copy-Item -Recurse (Join-Path $skillSrc "*") $dest
        Set-Content -Path (Join-Path $dest ".agentseed-plugin-root") -Value $pluginHome -NoNewline
        Write-Host "==> skill installed to $dest"
    }
    $serverPy = Join-Path $pluginHome "server\guard_server.py"
    $hookPy = Join-Path $pluginHome "server\guard_hook.py"
    $py = if ($env:PYTHON) { $env:PYTHON } else { "python" }

    switch ($Client) {
        "claude" {
            Install-Skill "$HOME\.claude\skills\verify-before-code"
            if ($Hooks) {
                & $py $hookPy register --client claude
                if ($LASTEXITCODE -ne 0) {
                    Write-Warning "hook registration failed; run: python `"$hookPy`" register --client claude"
                }
            }
            Write-Host ""
            Write-Host "==> final step - register the MCP server:"
            Write-Host "    claude mcp add agentseed -- python `"$serverPy`""
        }
        "opencode" {
            Install-Skill "$HOME\.config\opencode\skill\verify-before-code"
            if ($Hooks) { & $py $hookPy register --client opencode }
            Write-Host ""
            Write-Host "==> final step - add to ~/.config/opencode/opencode.json:"
            Write-Host "    `"mcp`": { `"agentseed`": { `"type`": `"local`","
            Write-Host "        `"command`": [`"python`", `"$serverPy`"], `"enabled`": true } }"
        }
        "cursor" {
            if ($Hooks) { & $py $hookPy register --client cursor }
            Write-Host "==> Cursor has no stable Agent Plugins directory yet."
            Write-Host "    Plugin kept at: $pluginHome"
            Write-Host "    Register the MCP server in Cursor settings:"
            Write-Host "      command: python  args: [$serverPy]"
        }
        default {
            $dest = if ($Dir) { Join-Path $Dir "AgentSeed" } else { Join-Path $PWD "AgentSeed" }
            if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dest) | Out-Null
            Copy-Item -Recurse $src $dest
            Write-Host "==> plugin copied to $dest"
            Write-Host "==> done. Drop it into your client, or re-run with -Client claude|opencode."
        }
    }
}
finally {
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}
