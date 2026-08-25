#!/usr/bin/env bash
# AgentSeed installer - download the latest release and wire it into a client.
#
# Usage: ./install.sh [--client claude|opencode|cursor|manual] [--dir TARGET]
#                     [--sha256 HEX] [--url ZIP_URL]
#                     [--repo owner/name] [--forge github|gitcode]
#
# --url   : download a specific release zip directly (any host). Skips repo
#           resolution entirely.
# --repo  : override the repository (default: badhope/AgentSeed, the canonical
#           GitCode home; weed33834/* on GitHub is a deprecated mirror).
# --forge : which release API to query (default: gitcode).
set -e
repo="badhope/AgentSeed"
forge="gitcode"
client="auto"
dir=""
want_sha=""
direct_url=""
while [ $# -gt 0 ]; do
  case "$1" in
    --client) client="$2"; shift 2 ;;
    --dir) dir="$2"; shift 2 ;;
    --sha256) want_sha="$2"; shift 2 ;;
    --url) direct_url="$2"; shift 2 ;;
    --repo) repo="$2"; shift 2 ;;
    --forge) forge="$2"; shift 2 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

if [ -n "$direct_url" ]; then
  url="$direct_url"
elif [ "$forge" = "gitcode" ]; then
  echo "==> resolving latest GitCode release of $repo"
  # GitCode v5 API (Gitee-compatible); /releases/latest 400s when empty.
  url=$(curl -fsSL "https://api.gitcode.com/api/v5/repos/$repo/releases?per_page=1" |
    grep -o '"browser_download_url": *"[^"]*\.zip"' | head -1 |
    sed 's/.*"\(https[^"]*\)"/\1/')
  [ -n "$url" ] || { echo "no .zip asset on the latest GitCode release" >&2; exit 1; }
else
echo "==> resolving latest release of $repo"
url=$(curl -fsSL "https://api.github.com/repos/$repo/releases/latest" |
  grep -o '"browser_download_url": *"[^"]*\.zip"' | head -1 |
  sed 's/.*"\(https[^"]*\)"/\1/')
[ -n "$url" ] || { echo "no .zip asset on the latest release" >&2; exit 1; }
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

# 1) stable full-plugin home (the MCP server runs from here)
plugin_home="${AGENTSEED_HOME:-$HOME/.agentseed}/AgentSeed"
mkdir -p "$(dirname "$plugin_home")"
rm -rf "$plugin_home"
cp -R "$src" "$plugin_home"
echo "==> full plugin installed to $plugin_home"

# 2) flat skill copy so clients that scan <dir>/SKILL.md find it
install_skill() {
  rm -rf "$1"
  mkdir -p "$1"
  cp -R "$plugin_home/skills/verify-before-code/"* "$1/"
  printf '%s' "$plugin_home" > "$1/.agentseed-plugin-root"
  echo "==> skill installed to $1"
}

case "$client" in
  claude)
    install_skill "$HOME/.claude/skills/verify-before-code"
    echo ""
    echo "==> final step - register the MCP server:"
    echo "    claude mcp add agentseed -- python \"$plugin_home/server/guard_server.py\""
    ;;
  opencode)
    install_skill "$HOME/.config/opencode/skill/verify-before-code"
    echo ""
    echo "==> final step - add to ~/.config/opencode/opencode.json:"
    cat <<EOF
    "mcp": {
      "agentseed": {
        "type": "local",
        "command": ["python", "$plugin_home/server/guard_server.py"],
        "enabled": true
      }
    }
EOF
    ;;
  cursor)
    echo "==> Cursor has no stable Agent Plugins directory yet."
    echo "    Plugin kept at: $plugin_home"
    echo "    Register the MCP server in Cursor settings:"
    echo "      command: python  args: [$plugin_home/server/guard_server.py]"
    ;;
  manual|auto)
    dest="${dir:-$PWD}/AgentSeed"
    mkdir -p "$(dirname "$dest")"
    rm -rf "$dest"
    cp -R "$src" "$dest"
    echo "==> plugin copied to $dest"
    echo "==> done. Drop it into your client, or re-run with --client claude|opencode."
    ;;
esac
