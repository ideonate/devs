FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    docker.io \
    && rm -rf /var/lib/apt/lists/*

# Install GitHub CLI
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update \
    && apt-get install gh -y

# Install DevContainer CLI
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g @devcontainers/cli

# Set working directory
WORKDIR /app

# Copy package files
COPY pyproject.toml README.md ./
COPY devs_webhook/ devs_webhook/

# Install Python dependencies
RUN pip install -e .

# Create directories
RUN mkdir -p /app/.devs-webhook/repos /app/.devs-webhook/workspaces

# Create non-root user for security
RUN useradd -m -u 1000 webhook && \
    chown -R webhook:webhook /app && \
    usermod -aG docker webhook

USER webhook

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# Run the webhook server
CMD ["devs-webhook", "serve"]