# ObsidianPalace — production image.
# Single container: nginx (SSL) + Node.js (obsidian-headless sync) + Python (MCP server).
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

# System dependencies — supervisor + nginx for SSL termination
RUN apt-get update && apt-get install -y --no-install-recommends \
    supervisor \
    nginx \
    findutils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python package
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# Supervisord config
COPY supervisord.conf /etc/supervisor/conf.d/obsidian-palace.conf

# Nginx config
COPY nginx.conf /etc/nginx/nginx.conf

# Entrypoint script
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Data directories (mounted as persistent disk in production)
RUN mkdir -p /data/vault /data/chromadb /var/www/certbot

# Ports: 80 (HTTP/ACME), 443 (HTTPS), 8080 (internal uvicorn)
EXPOSE 80 443

# Health check targets nginx → uvicorn
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import httpx; r = httpx.get('http://localhost:8080/health'); r.raise_for_status()"

ENTRYPOINT ["/app/entrypoint.sh"]
