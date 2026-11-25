#!/bin/bash
# Trust the stone-ingress CA (the Caddy internal root on the docker host) in the
# container's system store and the node user's Chromium NSS store, so curl,
# Node (--use-system-ca), and the visible Playwright browser accept the
# https://<dev-domain> certs without warnings. Best-effort and idempotent: skips
# quietly when the stone-ingress API isn't reachable (developing off stone-pc).
set -uo pipefail

GW=$(getent ahosts host.docker.internal 2>/dev/null | awk '{print $1; exit}')
[ -z "$GW" ] && GW=$(ip route show default 2>/dev/null | awk '/default/{print $3; exit}')
[ -z "$GW" ] && { echo "ℹ️  no gateway found — skipping stone-ingress CA trust"; exit 0; }

CRT=/usr/local/share/ca-certificates/stone-ingress.crt
if curl -fsS --connect-timeout 3 "http://$GW:8800/v1/ca.crt" -o "$CRT.tmp" 2>/dev/null; then
    if cmp -s "$CRT.tmp" "$CRT" 2>/dev/null; then
        rm -f "$CRT.tmp"
        echo "✅ stone-ingress CA already trusted"
    else
        mv "$CRT.tmp" "$CRT"
        update-ca-certificates >/dev/null 2>&1 || true
        echo "✅ stone-ingress CA installed into system trust store"
    fi
else
    rm -f "$CRT.tmp" 2>/dev/null || true
    echo "ℹ️  stone-ingress API not reachable at http://$GW:8800 — skipping CA trust"
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
