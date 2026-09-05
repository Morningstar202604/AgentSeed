#!/usr/bin/env bash
# AgentSeed installer - download the latest release and wire it into a client.
#
# Usage: ./install.sh [--client auto|claude|opencode|cursor|manual] [--dir TARGET]
#                     [--sha256 HEX] [--url ZIP_URL] [--hooks]
#                     [--repo owner/name]
#
# --url   : download a specific release zip directly (any host). Skips repo
#           resolution entirely.
# --repo  : override the repository (default: Morningstar202604/AgentSeed,
#           the canonical GitHub home).
# --hooks : additionally register the client-enforcement hook (Claude Code:
#           merges into ~/.claude/settings.json, idempotent, previous config
#           kept as settings.json.bak).
set -e
repo="Morningstar202604/AgentSeed"
client="auto"
dir=""
want_sha=""
direct_url=""
want_hooks=0
while [ $# -gt 0 ]; do
  case "$1" in
    --client) client="$2"; shift 2 ;;
    --dir) dir="$2"; shift 2 ;;
    --sha256) want_sha="$2"; shift 2 ;;
    --url) direct_url="$2"; shift 2 ;;
    --repo) repo="$2"; shift 2 ;;
    --hooks) want_hooks=1; shift ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

# Pick an interpreter that actually exists: `python3` is missing on plain
# Windows installs, `python` is missing on bare Debian/macOS.
resolve_python() {
  if [ -n "${PYTHON:-}" ]; then
    command -v "$PYTHON" >/dev/null 2>&1 || { echo "PYTHON=$PYTHON not found on PATH" >&2; exit 1; }
    echo "$PYTHON"
    return
  fi
  for cand in python3 python; do
    if command -v "$cand" >/dev/null 2>&1 && "$cand" -c 'import sys' >/dev/null 2>&1; then
      echo "$cand"
      return
    fi
  done
  echo ""
}

if [ -n "$direct_url" ]; then
  url="$direct_url"
else
  echo "==> resolving latest release of $repo"
  url=$(curl -fsSL "https://api.github.com/repos/$repo/releases/latest" |
    grep -o '"browser_download_url": *"[^"]*\.zip"' | head -1 |
    sed 's/.*"\(https[^"]*\)"/\1/')
  [ -n "$url" ] || { echo "no .zip asset on the latest $repo release" >&2; exit 1; }
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
echo "==> downloading $url"
curl -fsSL "$url" -o "$tmp/agentseed.zip"
if [ -n "$want_sha" ]; then
  if command -v sha256sum >/dev/null 2>&1; then
    got_sha=$(sha256sum "$tmp/agentseed.zip" | cut -d' ' -f1)
  elif command -v shasum >/dev/null 2>&1; then
    got_sha=$(shasum -a 256 "$tmp/agentseed.zip" | cut -d' ' -f1)
  else
    got_sha=$(openssl dgst -sha256 "$tmp/agentseed.zip" | sed 's/^.*= //')
  fi
  if [ "$got_sha" != "$(echo "$want_sha" | tr 'A-Z' 'a-z')" ]; then
    echo "checksum mismatch: expected $want_sha, got $got_sha" >&2
    exit 1
  fi
  echo "==> checksum verified"
else
  echo "WARNING: no --sha256 given; the archive is NOT integrity-checked." >&2
  echo "         Pin a release checksum to protect against tampering." >&2
fi
unzip -q "$tmp/agentseed.zip" -d "$tmp/x"
src=$(dirname "$(find "$tmp/x" -name plugin.json | head -1)")
[ -n "$src" ] || { echo "plugin.json not found in archive" >&2; exit 1; }

py="$(resolve_python)"
[ -n "$py" ] || { echo "no usable python3/python on PATH - set PYTHON=/path/to/python" >&2; exit 1; }

# Never blow away a previous install: move it aside so an upgrade is reversible.
backup_aside() {
  [ -e "$1" ] || return 0
  stamp=$(date +%Y%m%d-%H%M%S)
  mv "$1" "$1.bak-$stamp"
  echo "==> previous copy moved aside: $1.bak-$stamp"
}

# 1) stable full-plugin home (the MCP server runs from here)
plugin_home="${AGENTSEED_HOME:-$HOME/.agentseed}/AgentSeed"
mkdir -p "$(dirname "$plugin_home")"
backup_aside "$plugin_home"
cp -R "$src" "$plugin_home"
echo "==> full plugin installed to $plugin_home"

# 2) flat skill copy so clients that scan <dir>/SKILL.md find it
install_skill() {
  backup_aside "$1"
  mkdir -p "$1"
  cp -R "$plugin_home/skills/verify-before-code/"* "$1/"
  printf '%s' "$plugin_home" > "$1/.agentseed-plugin-root"
  echo "==> skill installed to $1"
}

case "$client" in
  claude)
    install_skill "$HOME/.claude/skills/verify-before-code"
    if [ "$want_hooks" = "1" ]; then
      "$py" "$plugin_home/server/guard_hook.py" register --client claude ||
        echo "WARNING: hook registration failed; run: $py \"$plugin_home/server/guard_hook.py\" register --client claude" >&2
    fi
    echo ""
    echo "==> final step - register the MCP server:"
    echo "    claude mcp add agentseed -- $py \"$plugin_home/server/guard_server.py\""
    ;;
  opencode)
    install_skill "$HOME/.config/opencode/skill/verify-before-code"
    if [ "$want_hooks" = "1" ]; then
      "$py" "$plugin_home/server/guard_hook.py" register --client opencode || true
    fi
    echo ""
    echo "==> final step - add to ~/.config/opencode/opencode.json:"
    cat <<EOF
    "mcp": {
      "agentseed": {
        "type": "local",
        "command": ["$py", "$plugin_home/server/guard_server.py"],
        "enabled": true
      }
    }
EOF
    ;;
  cursor)
    if [ "$want_hooks" = "1" ]; then
      "$py" "$plugin_home/server/guard_hook.py" register --client cursor || true
    fi
    echo "==> Cursor has no stable Agent Plugins directory yet."
    echo "    Plugin kept at: $plugin_home"
    echo "    Register the MCP server in Cursor settings:"
    echo "      command: $py  args: [$plugin_home/server/guard_server.py]"
    ;;
  manual|auto)
    dest="${dir:-$PWD}/AgentSeed"
    mkdir -p "$(dirname "$dest")"
    backup_aside "$dest"
    cp -R "$src" "$dest"
    echo "==> plugin copied to $dest"
    echo "==> interpreter detected for this machine: $py"
    echo "    Register the MCP server with:  $py \"$dest/server/guard_server.py\""
    echo "    (or, if you use an npm-based client: npx agentseed-mcp)"
    echo "==> done. Drop it into your client, or re-run with --client claude|opencode."
    ;;
esac
