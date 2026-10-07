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

# Gate on the same master switch as the rest of the Tailscale wiring.
case "${TS_ENABLE:-}" in
  1|true|yes) ;;
  *)
    echo "ℹ️  Tailscale not enabled (TS_ENABLE=${TS_ENABLE:-unset}) — skipping tailnet setup."
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

run_start_hooks
