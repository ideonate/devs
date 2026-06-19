#!/bin/bash
# Root helper (NOPASSWD sudo-script): start tailscaled as a detached daemon if it
# isn't already running. Runs as root so Tailscale SSH can open login sessions;
# uses userspace networking so no TUN device is required. Idempotent.
set -uo pipefail

SOCK="/var/run/tailscale/tailscaled.sock"
[ -S "$SOCK" ] && exit 0   # already running

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
