# ObsidianPalace — production image.
# Single container: Node.js (obsidian-headless sync) + Python (MCP server).
# Managed by supervisord.

# --- Stage 1: Node.js layer (obsidian-headless CLI) ---
FROM node:22-slim AS node-layer

RUN npm install -g obsidian-headless

# --- Stage 2: Python application ---
FROM python:3.12-slim-bookworm

# Copy Node.js runtime and obsidian-headless from the node stage
COPY --from=node-layer /usr/local/bin/node /usr/local/bin/node
COPY --from=node-layer /usr/local/lib/node_modules /usr/local/lib/node_modules
COPY --from=node-layer /usr/local/bin/npm /usr/local/bin/npm
# Symlink the ob CLI
RUN ln -s /usr/local/lib/node_modules/obsidian-headless/bin/ob.js /usr/local/bin/ob

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python package
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# Supervisord config
COPY supervisord.conf /etc/supervisor/conf.d/obsidian-palace.conf

# Data directories (mounted as persistent disk in production)
RUN mkdir -p /data/vault /data/chromadb

EXPOSE 8080

# Health check for GCE instance group
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import httpx; r = httpx.get('http://localhost:8080/health'); r.raise_for_status()"

CMD ["supervisord", "-n", "-c", "/etc/supervisor/conf.d/obsidian-palace.conf"]
