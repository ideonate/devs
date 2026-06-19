#!/bin/bash
# Convenience wrapper: talk to this container's (root) tailscaled via the NOPASSWD
# sudo-script. Symlinked to `ts` on PATH, e.g. `ts status`, `ts serve --bg 5173`.
exec sudo -n /usr/local/bin/ts-cli.sh "$@"
