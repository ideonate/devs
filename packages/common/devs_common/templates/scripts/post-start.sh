#!/bin/bash
# postStartCommand orchestrator (runs as the node user on every container start).
# Unprivileged: env/gating logic, then hands privileged work to root sudo-scripts.
#
# Why this runs on EVERY start (not just postCreate): a plain container restart
# (host reboot, `docker start`) re-runs only PID 1, not the devcontainer
# create-lifecycle. So tailscaled, the tailnet node and Tailscale SSH are all gone
# after a restart — and a VS Code Remote-SSH connection to that node then has
# nothing to reconnect to. Re-running the bring-up here restores it automatically.
# Every step is idempotent, so running it again right after postCreate (on first
# create) is a harmless no-op.
set -uo pipefail

# Same env source start-tailscale.sh reads TS_ENABLE/TS_AUTHKEY from.
if [ -f /home/node/.devs-env/.env ]; then
  set -a; . /home/node/.devs-env/.env; set +a
fi

# Per-developer start hooks: ~/.devs/envs/<project>/autoexec-start/ on the host.
# The every-start counterpart of the create-time autoexec/ — for whatever a hook
# launched that a restart kills along with everything else that isn't PID 1. Same
# runner; no directory => no-op. Called last on either path below, so a hook that
# needs tailnet names finds MagicDNS already in place.
run_start_hooks() {
  DEVS_AUTOEXEC_DIR=/home/node/.devs-env/autoexec-start /usr/local/bin/run-autoexec.sh \
    || echo "⚠️  autoexec-start hook failed (continuing)."
}

# VS Code machine settings (+ optional tmux overlay, off unless DEVS_TMUX=1). Not
# Tailscale-gated — it configures the editor regardless of how you connect. Must come
# before the TS_ENABLE gate below, which exits when Tailscale is off.
/usr/local/bin/setup-vscode-settings.sh || true

# Hermes Agent's default model, seeded into its host-persisted config if none is set yet.
/usr/local/bin/setup-hermes.sh || true

# stone-ingress (opt-in): STONE_INGRESS_URL in the devs env is the API base —
# http://host.docker.internal:8800 on stone-pc, or http://stone-pc.<tailnet>.ts.net:8800
# from elsewhere over the tailnet. Unset/off => nothing below runs. When set:
# trust its CA (so curl/Claude Code accept https://cairn.internal etc.), and if
# it's this container's own docker host, use stone-dns there as the first resolver.
STONE_API="${STONE_INGRESS_URL:-}"
case "$STONE_API" in ""|off|0|false|no) STONE_API="" ;; esac
setup_stone_ingress() {
  [ -n "$STONE_API" ] || return 0
  sudo -n /usr/local/bin/setup-stone-dns.sh "$STONE_API" || true
  sudo -n /usr/local/bin/trust-stone-ca.sh "$STONE_API" || true
}

# Gate on the same master switch as the rest of the Tailscale wiring.
case "${TS_ENABLE:-}" in
  1|true|yes) ;;
  *)
    echo "ℹ️  Tailscale not enabled (TS_ENABLE=${TS_ENABLE:-unset}) — skipping tailnet setup."
    setup_stone_ingress
    run_start_hooks
    exit 0 ;;
esac

# Re-join the tailnet (idempotent): ensures tailscaled is running — self-healing a
# stale socket left by the previous boot, see sudo-scripts/start-tailscaled.sh —
# then re-runs `tailscale up` (+ serve/funnel). The hostname derives from the same
# remoteEnv (DEVS_PROJECT_NAME/DEVCONTAINER_NAME) the create path uses, and the
# persisted /var/lib/tailscale state reclaims the same identity, so the node's
# name stays stable across restarts and rebuilds.
/usr/local/bin/start-tailscale.sh || true

# Prepend the MagicDNS resolver so tailnet split-DNS names resolve from inside the
# container. Must run after the bring-up above (it no-ops unless tailscaled is up),
# and on every start because Docker regenerates /etc/resolv.conf each time.
sudo -n /usr/local/bin/setup-magicdns.sh || true

# After MagicDNS (so stone-dns, when local, ends up first) and after the tailnet is
# up (so a tailnet STONE_INGRESS_URL is reachable for the CA fetch).
setup_stone_ingress

run_start_hooks
