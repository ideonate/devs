#!/bin/bash
# postStartCommand orchestrator (runs as the node user on every container start).
# Unprivileged: env/gating logic, then hands privileged work to a root sudo-script.
set -uo pipefail

# Same env source start-tailscale.sh reads TS_ENABLE/TS_AUTHKEY from.
if [ -f /home/node/.devs-env/.env ]; then
  set -a; . /home/node/.devs-env/.env; set +a
fi

# Gate on the same master switch as the rest of the Tailscale wiring.
case "${TS_ENABLE:-}" in
  1|true|yes) ;;
  *)
    echo "ℹ️  Tailscale not enabled (TS_ENABLE=${TS_ENABLE:-unset}) — skipping MagicDNS resolv.conf setup."
    exit 0 ;;
esac

sudo -n /usr/local/bin/setup-magicdns.sh || true
