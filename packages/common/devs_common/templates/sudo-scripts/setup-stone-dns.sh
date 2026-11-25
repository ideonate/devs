#!/bin/bash
# Root helper (NOPASSWD sudo-script): when the stone-ingress API is on this
# container's own docker host (stone-pc), put stone-dns — which listens on the
# same docker-bridge gateway — first in /etc/resolv.conf. stone-dns answers every
# *.internal name (cairn.internal, …), the tailnet split-DNS zones, ts.net, and
# forwards public names, so it works whether or not tailscaled is up.
#
# Usage: setup-stone-dns.sh API_URL   (e.g. http://host.docker.internal:8800)
#
# No-op when the API is elsewhere (e.g. over the tailnet from a Mac: MagicDNS
# then resolves the split-DNS names, see setup-magicdns.sh) or when stone-dns
# doesn't answer — never point the resolver at a dead server.
set -uo pipefail

API="${1:?usage: setup-stone-dns.sh API_URL}"
RESOLV=/etc/resolv.conf

HOST=$(printf '%s' "$API" | sed -E 's#^[a-zA-Z]+://##; s#[/:].*$##')
API_IP=$(getent ahostsv4 "$HOST" 2>/dev/null | awk '{print $1; exit}')
GW=$(ip route show default 2>/dev/null | awk '/default/{print $3; exit}')

if [ -z "$GW" ] || [ -z "$API_IP" ] || [ "$API_IP" != "$GW" ]; then
  echo "ℹ️  stone-ingress ($HOST) is not this container's docker host — leaving DNS as is."
  exit 0
fi

if ! dig +time=2 +tries=1 @"$GW" cloudflare.com A 2>/dev/null | grep -q 'status: NOERROR'; then
  echo "⚠️  stone-dns not answering on $GW:53 — leaving DNS as is."
  exit 0
fi

if grep -qE "^[[:space:]]*nameserver[[:space:]]+${GW//./\\.}([[:space:]]|\$)" "$RESOLV" \
    && [ "$(awk '/^[[:space:]]*nameserver/{print $2; exit}' "$RESOLV")" = "$GW" ]; then
  echo "✅ stone-dns ($GW) already first in $RESOLV — nothing to do."
  exit 0
fi

# Prepend; the existing servers stay below as the fallback. /etc/resolv.conf is a
# Docker bind mount, so rewrite it in place rather than mv'ing over the inode.
new=$({ printf 'nameserver %s\n' "$GW"; grep -vE "^[[:space:]]*nameserver[[:space:]]+${GW//./\\.}([[:space:]]|\$)" "$RESOLV"; })
printf '%s\n' "$new" > "$RESOLV"
echo "✅ stone-dns ($GW) is now the first resolver in $RESOLV."
