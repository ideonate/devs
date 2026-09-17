FROM node:22

# Timezone configuration
ARG TZ=Europe/London
ENV TZ="$TZ"
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone


# Install basic development tools and utilities
RUN apt update && apt install -y less \
  tzdata \
  git \
  procps \
  sudo \
  fzf \
  zsh \
  man-db \
  unzip \
  gnupg2 \
  gh \
  iptables \
  ipset \
  iproute2 \
  dnsutils \
  aggregate \
  jq \
  locales \
  python3.11 \
  python3-pip \
  python3.11-venv \
  python3.11-dev \
  build-essential \
  curl \
  wget \
  vim \
  nano \
  htop \
  tmux \
  ripgrep \
  && apt clean \
  && rm -rf /var/lib/apt/lists/*

# Install MariaDB (MySQL) and Redis
RUN apt update && \
  DEBIAN_FRONTEND=noninteractive apt install -y \
  mariadb-server \
  redis-server \
  && apt clean \
  && rm -rf /var/lib/apt/lists/*

# Create directories for MySQL and Redis data
RUN mkdir -p /var/lib/mysql /var/lib/redis /var/run/mysqld /var/run/redis \
  && chown -R mysql:mysql /var/lib/mysql /var/run/mysqld \
  && chown -R redis:redis /var/lib/redis /var/run/redis

# Configure MariaDB to listen on all interfaces
# Note: Removed skip-grant-tables so we can properly create users with passwords
# The start-services.sh script will handle user creation and authentication setup
RUN mkdir -p /etc/mysql/conf.d && \
  echo "[mysqld]" > /etc/mysql/conf.d/99-devcontainer.cnf && \
  echo "bind-address = 0.0.0.0" >> /etc/mysql/conf.d/99-devcontainer.cnf && \
  echo "port = 3306" >> /etc/mysql/conf.d/99-devcontainer.cnf

# Configure Redis to run as a daemon and bind to all interfaces
RUN sed -i 's/^bind .*/bind 0.0.0.0/' /etc/redis/redis.conf \
  && sed -i 's/^daemonize no/daemonize yes/' /etc/redis/redis.conf \
  && sed -i 's/^protected-mode yes/protected-mode no/' /etc/redis/redis.conf


# Configure locale
RUN echo "en_US.UTF-8 UTF-8" > /etc/locale.gen \
  && locale-gen \
  && update-locale LANG=en_US.UTF-8


# Ensure default node user has access to /usr/local/share
RUN mkdir -p /usr/local/share/npm-global && \
  chown -R node:node /usr/local/share

ARG USERNAME=node

# Persist bash history
RUN SNIPPET="export PROMPT_COMMAND='history -a' && export HISTFILE=/commandhistory/.bash_history" \
  && mkdir /commandhistory \
  && touch /commandhistory/.bash_history \
  && chown -R $USERNAME /commandhistory

# Set `DEVCONTAINER` environment variable to help with orientation
ENV DEVCONTAINER=true

# Create workspace and config directories and set permissions
RUN mkdir -p /workspaces /home/node/claudeconfig /home/node/codexconfig /home/node/hermesconfig \
      /home/node/.vscode-server/extensions \
      /home/node/.vscode-server/data/Machine && \
  echo '[]' > /home/node/.vscode-server/extensions/extensions.json && \
  chown -R node:node /workspaces /home/node /home/node/.vscode-server && \
  chmod 755 /workspaces

# Pre-install workspace-kind VS Code extensions so they're available on first connect.
# devcontainer.json's extensions list is only auto-installed by the Dev Containers
# extension; over an SSH remote it's silently skipped.
RUN for EXT in vscode-tmux-auto-reattach devs-bridge-drop; do \
      curl -fSL --retry 3 --compressed \
        "https://marketplace.visualstudio.com/_apis/public/gallery/publishers/ideonate/vsextensions/${EXT}/latest/vspackage" \
        -o /tmp/ext.vsix && \
      unzip -q /tmp/ext.vsix "extension/package.json" -d /tmp/ext-meta && \
      VERSION=$(node -e "console.log(require('/tmp/ext-meta/extension/package.json').version)") && \
      EXT_DIR="/home/node/.vscode-server/extensions/ideonate.${EXT}-${VERSION}" && \
      mkdir -p "${EXT_DIR}" && \
      unzip -q /tmp/ext.vsix "extension/*" -d /tmp/ext && \
      cp -r /tmp/ext/extension/. "${EXT_DIR}/" && \
      rm -rf /tmp/ext.vsix /tmp/ext /tmp/ext-meta; \
    done && \
    chown -R node:node /home/node/.vscode-server/extensions/
COPY register-vscode-extensions.js /tmp/
RUN node /tmp/register-vscode-extensions.js && rm /tmp/register-vscode-extensions.js && \
    chown node:node /home/node/.vscode-server/extensions/extensions.json

WORKDIR /workspaces

# Install git-delta for better git diffs
RUN ARCH=$(dpkg --print-architecture) && \
  wget "https://github.com/dandavison/delta/releases/download/0.18.2/git-delta_0.18.2_${ARCH}.deb" && \
  sudo dpkg -i "git-delta_0.18.2_${ARCH}.deb" && \
  rm "git-delta_0.18.2_${ARCH}.deb"

# Set up non-root user
USER node

# Install global packages
ENV NPM_CONFIG_PREFIX=/usr/local/share/npm-global
ENV PATH=$PATH:/usr/local/share/npm-global/bin

# Set the default shell to zsh
ENV SHELL=/bin/zsh

# Install zsh with plugins and theme
RUN sh -c "$(wget -O- https://github.com/deluan/zsh-in-docker/releases/download/v1.2.0/zsh-in-docker.sh)" -- \
  -p git \
  -p fzf \
  -a "source /usr/share/doc/fzf/examples/key-bindings.zsh" \
  -a "source /usr/share/doc/fzf/examples/completion.zsh" \
  -a "export PROMPT_COMMAND='history -a' && export HISTFILE=/commandhistory/.bash_history" \
  -x

# Install Claude CLI via native installer
RUN curl -fsSL https://claude.ai/install.sh | bash

# Install OpenAI Codex CLI. Pinned: an unpinned install silently followed upstream
# flag changes, which is how the old `--full-auto` alias below ended up broken.
ARG CODEX_CLI_VERSION=0.144.6
RUN npm install -g "@openai/codex@${CODEX_CLI_VERSION}"

# Install Hermes Agent (Nous Research's open-source coding agent). Pinned to a release
# tag for the same reason as Codex above; bump HERMES_AGENT_VERSION to upgrade. Setup
# wizard, browser and computer-use extras are skipped — the agent is driven through
# OpenRouter: put OPENROUTER_API_KEY in ~/.devs/envs/<project>/.env (or DEVS.yml env_vars).
#
# The code goes in /home/node/.hermes-agent and the data dir (HERMES_HOME: sessions,
# memory, skills, config.yaml) in /home/node/hermesconfig, which devcontainer.json
# bind-mounts from ~/.devs/hermesconfig so it persists across rebuilds like claudeconfig
# and codexconfig. The installer's default puts the code *inside* HERMES_HOME, where the
# mount would hide it. Because config.yaml lives on the host, the default model can't be
# baked in here: scripts/setup-hermes.sh seeds HERMES_DEFAULT_MODEL into it at container
# start if no model is configured yet. HERMES_INFERENCE_MODEL overrides it per container.
ARG HERMES_AGENT_VERSION=v2026.9.14
ARG HERMES_DEFAULT_MODEL=z-ai/glm-5.3
ENV HERMES_HOME=/home/node/hermesconfig \
    HERMES_DEFAULT_MODEL=${HERMES_DEFAULT_MODEL}
# Download first rather than `curl | bash`: /bin/sh has no pipefail, so a failed
# download (e.g. a GitHub 429) would otherwise run an empty script and "succeed".
# The installer also seeds a data dir (~85 MB: its own uv, skills, a sample config.yaml);
# the mount would hide it anyway, so point that at a scratch dir and delete it. Hermes
# re-syncs bundled skills into the mounted HERMES_HOME on first run.
RUN curl -fsSL --retry 5 --retry-delay 10 --retry-all-errors \
      "https://raw.githubusercontent.com/NousResearch/hermes-agent/${HERMES_AGENT_VERSION}/scripts/install.sh" \
      -o /tmp/hermes-install.sh && \
  HERMES_HOME=/tmp/hermes-build-home bash /tmp/hermes-install.sh \
    --branch "${HERMES_AGENT_VERSION}" --dir /home/node/.hermes-agent \
    --hermes-home /tmp/hermes-build-home \
    --non-interactive --skip-setup --skip-browser --skip-computer-use && \
  HERMES_HOME=/tmp/hermes-build-home /home/node/.local/bin/hermes --version && \
  rm -rf /tmp/hermes-install.sh /tmp/hermes-build-home

# Install cloudflared for tunnel support (proxies all HTTP methods correctly)
# Install VS Code CLI for tunnel support (needs root for /usr/local/bin)
# Using the standalone CLI which supports the 'tunnel' command
USER root
RUN ARCH=$(dpkg --print-architecture) && \
  curl -fSL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${ARCH}" -o /usr/local/bin/cloudflared && \
  chmod +x /usr/local/bin/cloudflared

RUN ARCH=$(dpkg --print-architecture) && \
  if [ "$ARCH" = "amd64" ]; then \
    curl -fSL 'https://update.code.visualstudio.com/latest/cli-linux-x64/stable' -o /tmp/vscode-cli.tar.gz; \
  elif [ "$ARCH" = "arm64" ]; then \
    curl -fSL 'https://update.code.visualstudio.com/latest/cli-linux-arm64/stable' -o /tmp/vscode-cli.tar.gz; \
  fi && \
  tar -xf /tmp/vscode-cli.tar.gz -C /usr/local/bin && \
  rm /tmp/vscode-cli.tar.gz && \
  chmod +x /usr/local/bin/code

# Install Tailscale (static binaries) so each devcontainer can join the tailnet
# as its own node in userspace-networking mode — see scripts/start-tailscale.sh.
# Pinned for reproducible builds; bump as needed.
ARG TAILSCALE_VERSION=1.98.4
RUN ARCH=$(dpkg --print-architecture) && \
  curl -fSL --retry 5 --retry-delay 5 --retry-all-errors --connect-timeout 30 \
    "https://pkgs.tailscale.com/stable/tailscale_${TAILSCALE_VERSION}_${ARCH}.tgz" -o /tmp/tailscale.tgz && \
  tar -xzf /tmp/tailscale.tgz -C /tmp && \
  mv "/tmp/tailscale_${TAILSCALE_VERSION}_${ARCH}/tailscale" "/tmp/tailscale_${TAILSCALE_VERSION}_${ARCH}/tailscaled" /usr/local/bin/ && \
  rm -rf /tmp/tailscale.tgz "/tmp/tailscale_${TAILSCALE_VERSION}_${ARCH}" && \
  chmod +x /usr/local/bin/tailscale /usr/local/bin/tailscaled

# Set up environment variables and aliases for Claude, Codex and Hermes
RUN for shell_rc in /home/node/.zshrc /home/node/.bashrc; do \
  echo "export CLAUDE_CONFIG_DIR=\"/home/node/claudeconfig\"" >> "$shell_rc" && \
  echo "export CODEX_HOME=\"/home/node/codexconfig\"" >> "$shell_rc" && \
  echo "export PATH=\"/home/node/.local/bin:\$PATH\"" >> "$shell_rc" && \
  echo "alias claude=\"claude --dangerously-skip-permissions\"" >> "$shell_rc" && \
  echo "alias codex=\"/usr/local/share/npm-global/bin/codex -c check_for_update_on_startup=false --dangerously-bypass-approvals-and-sandbox\"" >> "$shell_rc" && \
  echo "alias codex-normal=\"/usr/local/share/npm-global/bin/codex -c check_for_update_on_startup=false\"" >> "$shell_rc" && \
  echo "alias hermes='/home/node/.local/bin/hermes --yolo \${HERMES_INFERENCE_MODEL:+--model=\$HERMES_INFERENCE_MODEL}'" >> "$shell_rc" && \
  echo "alias hermes-normal='/home/node/.local/bin/hermes \${HERMES_INFERENCE_MODEL:+--model=\$HERMES_INFERENCE_MODEL}'" >> "$shell_rc" && \
  echo "" >> "$shell_rc" && \
  echo "# Auto-activate Python venv if it exists" >> "$shell_rc" && \
  echo "if [ -f /home/node/.devs-venv/workspace-venv/bin/activate ]; then" >> "$shell_rc" && \
  echo "    source /home/node/.devs-venv/workspace-venv/bin/activate" >> "$shell_rc" && \
  echo "fi" >> "$shell_rc" && \
  echo "# Set TEST_RESULTS_FOLDER" >> "$shell_rc" && \
  echo "export TEST_RESULTS_FOLDER=\"/home/node/bridge/test-results\"" >> "$shell_rc"; \
  done

# tmux defaults: mouse scrolling, deep scrollback, and live tab titles. Pairs with the
# ideonate.vscode-tmux-auto-reattach extension (liveTitles mode). Present regardless of
# DEVS_TMUX — this only shapes tmux when you actually run it.
RUN printf '%s\n' \
  'set -g mouse on' \
  'set -g history-limit 50000' \
  'bind m set -g mouse \; display "mouse #{?mouse,on,off}"' \
  'set -g set-titles on' \
  "set -g set-titles-string '#{session_name}: #{pane_current_command}'" \
  > /home/node/.tmux.conf && \
  chown node:node /home/node/.tmux.conf

# VS Code settings live here rather than in devcontainer.json's
# customizations.vscode.settings, because that block is only applied by the Dev
# Containers extension — a Remote-SSH connection (e.g. over Tailscale SSH) never reads
# devcontainer.json. Baking them as machine settings covers both paths. Both files also
# land in /etc/devcontainer-config/ so scripts/setup-vscode-settings.sh can re-deploy
# them at container start with the optional tmux overlay (DEVS_TMUX=1) applied.
# See templates/README-vscode-settings.md.
COPY --chown=node:node machine-settings.json /home/node/.vscode-server/data/Machine/settings.json
COPY machine-settings.json machine-settings.tmux.json /etc/devcontainer-config/

# Copy and set up scripts
COPY scripts/ /usr/local/bin/
COPY sudo-scripts/ /usr/local/bin/
RUN chmod +x /usr/local/bin/*.sh /usr/local/bin/*.py && \
  ln -sf /usr/local/bin/ts.sh /usr/local/bin/ts
COPY sudo-scripts/ /tmp/sudo-scripts-list/
RUN echo "DEBUG: Files that need sudo:" && ls -la /tmp/sudo-scripts-list/ && \
  { echo "# Allow node user to run sudo scripts without password"; \
  ls /tmp/sudo-scripts-list/ | sed 's/^/node ALL=(root) NOPASSWD: \/usr\/local\/bin\//'; \
  } > /etc/sudoers.d/node-scripts && \
  echo "DEBUG: Generated sudoers file:" && cat /etc/sudoers.d/node-scripts && \
  chmod 0440 /etc/sudoers.d/node-scripts && \
  rm -rf /tmp/sudo-scripts-list

USER node
