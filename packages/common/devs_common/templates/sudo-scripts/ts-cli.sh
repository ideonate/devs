#!/bin/bash
# Root helper (NOPASSWD sudo-script): run the tailscale CLI against the container's
# root daemon socket. The node-user `ts` wrapper calls this; start-tailscale.sh
# uses it for up/serve/status.
exec /usr/local/bin/tailscale --socket=/var/run/tailscale/tailscaled.sock "$@"
