FROM mcr.microsoft.com/devcontainers/python:2-3.14-trixie

COPY .devcontainer/entrypoint.sh /usr/local/bin/devcontainer-entrypoint.sh
RUN chmod +x /usr/local/bin/devcontainer-entrypoint.sh

# Install Node.js (LTS), PostgreSQL client, and ngrok
RUN rm -f /etc/apt/sources.list.d/yarn.list \
    && apt-get update \
    && apt-get install -y curl postgresql-client \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc \
        | tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null \
    && echo "deb https://ngrok-agent.s3.amazonaws.com buster main" \
        > /etc/apt/sources.list.d/ngrok.list \
    && apt-get update \
    && apt-get install -y ngrok \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && ln -s /root/.local/bin/uv /usr/local/bin/uv

# Install Python dependencies
COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

# Install Node dependencies and build CSS
COPY package.json package-lock.json* ./
RUN npm install --silent
COPY webapp/static/css/src/input.css webapp/static/css/src/input.css
RUN npm run build:css

# Expose application port
EXPOSE 8100

# Default command: run the startup script (repo must be mounted at /workspace)
ENTRYPOINT ["/usr/local/bin/devcontainer-entrypoint.sh"]
CMD ["/workspace/start.sh"]
