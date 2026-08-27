#!/usr/bin/env bash
# AgentSeed quick check - validate the plugin in the given directory.
# Usage:
#   ./check.sh [--strict] [plugin-dir]
#   ./check.sh --self-test      # assert the bundled example fixtures behave
#
# Locates server/guard_cli.py by walking up from this script to a directory
# that ships it (repo root has it). That breaks when the skill is installed
# standalone, so we also fall back to the plugin home recorded in a
# `.agentseed-plugin-root` file next to SKILL.md (written by the installers),
# then to $HOME/.agentseed/AgentSeed. Override with AGENTSEED_PLUGIN_ROOT.
set -e
here="$(cd "$(dirname "$0")" && pwd)"

# --- locate the CLI (POSIX sh, zero dependencies) ---
has_cli() { [ -n "$1" ] && [ -f "$1/server/guard_cli.py" ]; }

cli=""
if has_cli "${AGENTSEED_PLUGIN_ROOT:-}"; then
  cli="$AGENTSEED_PLUGIN_ROOT/server/guard_cli.py"
fi
if [ -z "$cli" ]; then
  d="$here"
  i=0
  while [ "$d" != "/" ] && [ "$i" -lt 6 ]; do
    if has_cli "$d"; then cli="$d/server/guard_cli.py"; break; fi
    d="$(dirname "$d")"
    i=$((i + 1))
  done
fi
if [ -z "$cli" ]; then
  for pf in "$here/../.agentseed-plugin-root" "$here/.agentseed-plugin-root"; do
    if [ -f "$pf" ]; then
      root="$(tr -d '\r\n' < "$pf")"
      if has_cli "$root"; then cli="$root/server/guard_cli.py"; break; fi
    fi
  done
fi
if [ -z "$cli" ]; then
  default_root="${HOME:-~}/.agentseed/AgentSeed"
  if has_cli "$default_root"; then cli="$default_root/server/guard_cli.py"; fi
fi

if [ -z "$cli" ]; then
  echo "error: cannot locate server/guard_cli.py." >&2
  echo "Fix: install the full AgentSeed plugin, set AGENTSEED_PLUGIN_ROOT to" >&2
  echo "its directory, or clone it to \$HOME/.agentseed/AgentSeed." >&2
  exit 2
fi
plugin_root="$(cd "$(dirname "$cli")/.." && pwd)"

# --- interpreter probe: honour PYTHON, else the first candidate that ACTUALLY
# runs a trivial import. `command -v` alone is not enough: the Microsoft Store
# python3 stub exists on PATH but exits non-zero, so we run "-c import sys". ---
runnable() { command -v "$1" >/dev/null 2>&1 && "$1" -c "import sys" >/dev/null 2>&1; }

if [ -n "${PYTHON:-}" ]; then
  py="$PYTHON"
  if ! runnable "$py"; then
    echo "error: PYTHON=$py is set but cannot run (missing or a WindowsApps stub?)." >&2
    exit 2
  fi
else
  py=""
  for cand in python3 python; do
    if runnable "$cand"; then py="$cand"; break; fi
  done
  if [ -z "$py" ]; then
    echo "error: no working Python interpreter (tried python3, python). Set PYTHON." >&2
    exit 2
  fi
fi

# --- self-test: the examples/plugins fixtures must behave as documented ---
if [ "${1:-}" = "--self-test" ]; then
  set +e
  good="$plugin_root/examples/plugins/good-plugin"
  broken="$plugin_root/examples/plugins/broken-plugin"
  out="$(mktemp)"
  rc=0

  "$py" "$cli" check "$good" > "$out" 2>&1
  good_rc=$?
  if [ "$good_rc" -ne 0 ] || ! grep -q '"ok": true' "$out"; then
    echo "FAIL: good-plugin must report ok:true (exit 0)" >&2
    cat "$out" >&2
    rc=1
  else
    echo "PASS: good-plugin reports ok:true"
  fi

  "$py" "$cli" check "$broken" > "$out" 2>&1
  broken_rc=$?
  if [ "$broken_rc" -eq 0 ] || ! grep -q '"ok": false' "$out"; then
    echo "FAIL: broken-plugin must report errors (ok:false, exit != 0)" >&2
    cat "$out" >&2
    rc=1
  else
    echo "PASS: broken-plugin fails as expected"
  fi

  rm -f "$out"
  [ "$rc" -eq 0 ] && echo "self-test: OK (interpreter=$py, plugin-root=$plugin_root)"
  exit "$rc"
fi

# --- normal validate path ---
if [ "${1:-}" = "--strict" ]; then
  target="${2:-.}"
  "$py" "$cli" check "$target"
  exec "$py" "$cli" scan "$target" --strict
else
  exec "$py" "$cli" check "${1:-.}"
fi
