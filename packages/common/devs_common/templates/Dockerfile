FROM node:20

ARG TZ
ENV TZ="$TZ"


# Install basic development tools and utilities
RUN apt update && apt install -y less \
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
  && apt clean \
  && rm -rf /var/lib/apt/lists/*

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
RUN mkdir -p /workspaces /home/node/claudeconfig /home/node/.vscode-server/extensions && \
  echo '[]' > /home/node/.vscode-server/extensions/extensions.json && \
  chown -R node:node /workspaces /home/node /home/node/.vscode-server && \
  chmod 755 /workspaces

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

# Install Claude CLI
RUN npm install -g @anthropic-ai/claude-code

# Set up environment variables for Claude
USER root
RUN echo "export CLAUDE_CONFIG_DIR=\"/home/node/claudeconfig\"" >> /home/node/.zshrc && \
  echo "export CLAUDE_CONFIG_DIR=\"/home/node/claudeconfig\"" >> /home/node/.bashrc


# Copy and set up scripts
COPY init-firewall.sh setup-workspace.sh webapp-screenshot.py screenshot-webapp.sh python-venv-integration.sh copy-ssh.sh post-create-wrapper.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/init-firewall.sh /usr/local/bin/setup-workspace.sh /usr/local/bin/webapp-screenshot.py /usr/local/bin/screenshot-webapp.sh /usr/local/bin/python-venv-integration.sh /usr/local/bin/copy-ssh.sh /usr/local/bin/post-create-wrapper.sh && \
  echo "node ALL=(root) NOPASSWD: /usr/local/bin/init-firewall.sh, /usr/local/bin/setup-workspace.sh" > /etc/sudoers.d/node-scripts && \
  chmod 0440 /etc/sudoers.d/node-scripts

USER node