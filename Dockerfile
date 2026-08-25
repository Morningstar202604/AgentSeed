# Used by indexers (e.g. Glama) that build and probe MCP servers in containers.
# AgentSeed is pure-Python stdlib, so the image is trivial.
FROM python:3.12-slim

WORKDIR /app
COPY server/ ./server/
COPY skills/ ./skills/
COPY plugin.json mcp.json ./

# Run as an unprivileged user (stdio server needs no ports or root).
RUN useradd --create-home --uid 10001 seed
USER seed

# MCP stdio transport: the indexer sends JSON-RPC over stdin/stdout.
# Healthcheck: the engine must import cleanly in this image.
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s \
  CMD ["python", "-c", "import sys; sys.path.insert(0, 'server'); import guard_engine"]
CMD ["python", "server/guard_server.py"]
