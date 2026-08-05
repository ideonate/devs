#!/bin/bash
# Root helper (NOPASSWD sudo-script): start tailscaled as a detached daemon if it
# isn't already running. Runs as root so Tailscale SSH can open login sessions;
# uses userspace networking so no TUN device is required. Idempotent.
set -uo pipefail

SOCK="/var/run/tailscale/tailscaled.sock"

# Idempotency / self-heal. Only skip if a tailscaled is ACTUALLY running. A plain
# container restart (host reboot, `docker start`) re-runs only PID 1 — the daemon
# process is gone, but its socket file persists on the container's writable layer.
# A naive "socket exists => already up" check then sees that stale socket, skips
# startup, and every subsequent `tailscale up` fails with "failed to connect to
# local tailscaled". So probe for a live daemon; if the socket is stale, remove it
# and start fresh.
if [ -S "$SOCK" ]; then
  if pgrep -x tailscaled >/dev/null 2>&1; then
    exit 0   # a real daemon is running — nothing to do
  fi
  echo "Removing stale tailscaled socket (no tailscaled process is running)…"
  rm -f "$SOCK"
fi

# setsid + </dev/null detaches the daemon from the calling exec session so it
# survives after postCreate (or whoever invoked it) exits.
setsid /usr/local/bin/tailscaled \
  --tun=userspace-networking \
  --socket="$SOCK" \
  --statedir=/var/lib/tailscale \
  </dev/null >>/var/log/tailscaled.log 2>&1 &
disown 2>/dev/null || true

for _ in $(seq 1 30); do
  [ -S "$SOCK" ] && break
  sleep 0.5
done
