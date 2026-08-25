#!/usr/bin/env bash
# AgentSeed release wrapper — delegates to scripts/pack.py (zero-dep Python).
# Usage: ./release.sh [--check-only]
set -e
PY="${PYTHON:-python3}"
DIR="$(cd "$(dirname "$0")" && pwd)"
if [ "$1" = "--check-only" ]; then
  "$PY" "$DIR/pack.py" --check-only
else
  "$PY" "$DIR/pack.py"
fi
