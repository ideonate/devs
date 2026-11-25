#!/bin/bash
# Trust the stone-ingress CA (the Caddy internal root on stone-pc) in the
# container's system store and the node user's Chromium NSS store, so curl,
# Claude Code / Node, and the visible Playwright browser accept the
# https://<dev-domain> and *.internal certs without warnings. Best-effort and
# idempotent: skips quietly when the stone-ingress API isn't reachable.
#
# Usage: trust-stone-ca.sh [API_URL]
#   API_URL is the stone-ingress API base, e.g. http://host.docker.internal:8800
#   on stone-pc or http://stone-pc.<tailnet>.ts.net:8800 over the tailnet. It
#   defaults to http://<docker gateway>:8800 (the container is on stone-pc).
set -uo pipefail

API="${1:-}"
if [ -z "$API" ]; then
    GW=$(getent ahosts host.docker.internal 2>/dev/null | awk '{print $1; exit}')
    [ -z "$GW" ] && GW=$(ip route show default 2>/dev/null | awk '/default/{print $3; exit}')
    [ -z "$GW" ] && { echo "ℹ️  no gateway found — skipping stone-ingress CA trust"; exit 0; }
    API="http://$GW:8800"
fi
API="${API%/}"

CRT=/usr/local/share/ca-certificates/stone-ingress.crt
if curl -fsS --connect-timeout 3 --max-time 10 "$API/v1/ca.crt" -o "$CRT.tmp" 2>/dev/null \
    && openssl x509 -in "$CRT.tmp" -noout 2>/dev/null; then
    if cmp -s "$CRT.tmp" "$CRT" 2>/dev/null; then
        rm -f "$CRT.tmp"
        echo "✅ stone-ingress CA already trusted"
    else
        mv "$CRT.tmp" "$CRT"
        update-ca-certificates >/dev/null 2>&1 || true
        echo "✅ stone-ingress CA installed into system trust store (from $API)"
    fi
else
    rm -f "$CRT.tmp" 2>/dev/null || true
    echo "ℹ️  stone-ingress API not reachable at $API — skipping CA trust"
fi

# Chromium on Linux uses the user's NSS database rather than Debian's CA bundle.
# The headed Playwright browser runs as node, so import the same root there. This
# fixes the visible "certificate invalid" indicator; ignore_https_errors remains a
# portability fallback for containers running away from stone-pc.
if command -v certutil >/dev/null 2>&1 && [ -f "$CRT" ]; then
    NSS_DIR=/home/node/.pki/nssdb
    install -d -m 700 -o node -g node "$NSS_DIR"
    if [ ! -f "$NSS_DIR/cert9.db" ]; then
        runuser -u node -- certutil -N -d "sql:$NSS_DIR" --empty-password
    fi
    runuser -u node -- certutil -D -d "sql:$NSS_DIR" -n stone-ingress >/dev/null 2>&1 || true
    runuser -u node -- certutil -A -d "sql:$NSS_DIR" -n stone-ingress -t "C,," -i "$CRT"
    echo "✅ stone-ingress CA installed into Chromium NSS trust store"
fi
