#!/bin/bash
# Deploy VS Code machine settings, applying the optional tmux overlay.
#
# Settings live in ~/.vscode-server/data/Machine/settings.json rather than in
# devcontainer.json's customizations.vscode.settings, because that block is applied by
# the Dev Containers extension only — a Remote-SSH connection (e.g. over Tailscale SSH)
# never reads devcontainer.json. See templates/README-vscode-settings.md.
#
# The Dockerfile already bakes the base file, so a container is correctly configured even
# if this never runs. This script exists for the DEVS_TMUX toggle: it re-deploys the base
# and merges machine-settings.tmux.json over it when tmux is requested, so switching is a
# container restart rather than an image rebuild.
#
#   DEVS_TMUX   "1"/"true"/"yes" => tmux becomes the default terminal profile and
#               ideonate.vscode-tmux-auto-reattach reattaches sessions on window load.
#               OFF by default: the tmux profile is defined either way, so you can pick
#               it from the terminal dropdown without opting in globally.
set -uo pipefail

BASE=/etc/devcontainer-config/machine-settings.json
OVERLAY=/etc/devcontainer-config/machine-settings.tmux.json
DEST=/home/node/.vscode-server/data/Machine/settings.json

[ -f "$BASE" ] || exit 0

# Same env source the other devs container scripts read their switches from.
if [ -f /home/node/.devs-env/.env ]; then
  set -a; . /home/node/.devs-env/.env; set +a
fi

mkdir -p "$(dirname "$DEST")"

case "${DEVS_TMUX:-}" in
  1|true|yes)
    if [ -f "$OVERLAY" ] && node -e '
      const fs = require("fs");
      const [base, overlay, dest] = process.argv.slice(1);
      const merged = {
        ...JSON.parse(fs.readFileSync(base, "utf8")),
        ...JSON.parse(fs.readFileSync(overlay, "utf8")),
      };
      fs.writeFileSync(dest, JSON.stringify(merged, null, 2) + "\n");
    ' "$BASE" "$OVERLAY" "$DEST"; then
      echo "🖥️  VS Code settings deployed (tmux enabled — DEVS_TMUX=${DEVS_TMUX})."
    else
      cp "$BASE" "$DEST"
      echo "⚠️  tmux overlay merge failed — deployed base VS Code settings instead."
    fi
    ;;
  *)
    cp "$BASE" "$DEST"
    echo "🖥️  VS Code settings deployed (tmux off; set DEVS_TMUX=1 to enable)."
    ;;
esac
