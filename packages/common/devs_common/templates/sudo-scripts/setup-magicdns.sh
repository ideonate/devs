#!/bin/bash
# Root helper (NOPASSWD sudo-script): make the container resolve the Tailscale
# split-DNS sample-app hostnames by prepending the MagicDNS resolver
# (100.100.100.100) to /etc/resolv.conf. See the "Split-DNS / MagicDNS" section
# of the devs Tailscale docs (docs/tailscale-setup.md) for the why.
set -uo pipefail

RESOLV=/etc/resolv.conf
MAGICDNS=100.100.100.100
SOCK=/var/run/tailscale/tailscaled.sock

# No-op unless Tailscale is actually up — otherwise we'd point the resolver at an
# unreachable server and stall every lookup behind a timeout.
if [ ! -S "$SOCK" ] || ! /usr/local/bin/tailscale --socket="$SOCK" status >/dev/null 2>&1; then
  echo "ℹ️  Tailscale not up — skipping MagicDNS resolv.conf setup."
  exit 0
fi

# Already prepended? (an uncommented `nameserver 100.100.100.100` line)
if grep -qE "^[[:space:]]*nameserver[[:space:]]+${MAGICDNS}([[:space:]]|\$)" "$RESOLV"; then
  echo "✅ MagicDNS resolver already present in $RESOLV — nothing to do."
  exit 0
fi

# Prepend as the first nameserver. glibc reads nameserver lines in order and, on
# MagicDNS SERVFAIL for non-tailnet names, falls through to the ISP servers that
# remain below. /etc/resolv.conf is a Docker bind mount, so we rewrite it in place
# (truncate + write) rather than mv'ing a new file over the mounted inode.
new=$({ printf 'nameserver %s\n' "$MAGICDNS"; cat "$RESOLV"; })
printf '%s\n' "$new" > "$RESOLV"
echo "✅ Prepended MagicDNS resolver ($MAGICDNS) to $RESOLV for tailnet split-DNS."
