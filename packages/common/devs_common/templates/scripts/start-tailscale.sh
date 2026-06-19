#!/bin/bash
# Join this devcontainer to the user's tailnet as its own node, and optionally
# publish a port over HTTPS (serve/funnel) and/or accept Tailscale SSH. Invoked
# (as the node user) from post-create-wrapper.sh. Safe no-op unless TS_ENABLE=1.
#
# This orchestrator runs unprivileged and does the env/gating/hostname logic; the
# privileged bits go through root sudo-scripts (start-tailscaled.sh / ts-cli.sh),
# matching the init-firewall pattern. tailscaled runs as root in userspace
# networking mode — no TUN device needed, and root is what lets Tailscale SSH open
# login sessions.
#
# Config — all via env. The natural place to set these is the per-project env
# file ~/.devs/envs/<project>/.env on the host, which devs mounts at
# /home/node/.devs-env/.env and which this script sources below:
#   TS_ENABLE      master switch, STRICTLY OPT-IN. Off unless set to
#                  "1"/"true"/"yes". A key alone does NOT enable Tailscale, so an
#                  auth key can live in the shared default .env harmlessly until a
#                  given project sets TS_ENABLE=1.
#   TS_AUTHKEY     (required when enabled) ephemeral, tagged auth key from the
#                  Tailscale admin console. Enabled but no key => warn + exit 0.
#   TS_HOSTNAME    tailnet hostname. Default: <DEVS_PROJECT_NAME>-<DEVCONTAINER_NAME>
#                  (e.g. myorg-myapp-alice) -> <name>.<tailnet>.ts.net.
#                  Dev name alone isn't unique across projects, hence the prefix.
#   TS_TAGS        advertised tags (default: tag:devcontainer). Must match the
#                  tagOwners in your tailnet ACL and the auth key's tag.
#   TS_SERVE_PORT  if set, serve this local port over HTTPS on the node's name.
#   TS_FUNNEL      "1"/"true": expose TS_SERVE_PORT to the PUBLIC internet
#                  (Funnel) instead of tailnet-only serve.
#   TS_SSH         "1"/"true": accept Tailscale SSH into the container (needs an
#                  `ssh` rule in the tailnet ACL allowing the `node` user).
set -uo pipefail

# Pull in secrets/config from the mounted devs env file, if present.
if [ -f /home/node/.devs-env/.env ]; then
  set -a; . /home/node/.devs-env/.env; set +a
fi

# Master switch — strictly opt-in, off by default (like the firewall). A key
# alone does NOT enable it, so a tailnet auth key can sit in the shared default
# .env harmlessly until a project explicitly sets TS_ENABLE=1.
case "${TS_ENABLE:-}" in
  1|true|yes) ;;
  *)
    echo "ℹ️  Tailscale not enabled (TS_ENABLE=${TS_ENABLE:-unset}) — skipping."
    echo "    Set TS_ENABLE=1 (+ TS_AUTHKEY) to join the tailnet."
    exit 0 ;;
esac

if [ -z "${TS_AUTHKEY:-}" ]; then
  echo "⚠️  TS_ENABLE is set but TS_AUTHKEY is missing — skipping Tailscale."
  echo "    Add an ephemeral, tagged key to a mounted .env (e.g. ~/.devs/envs/default/.env)."
  exit 0
fi

SSH_ON=""
case "${TS_SSH:-}" in 1|true|yes) SSH_ON=1 ;; esac

# tailscale CLI against the root daemon, via the NOPASSWD sudo-script.
TS=(sudo -n /usr/local/bin/ts-cli.sh)

# Derive a DNS-safe hostname. Prefer an explicit override; else <project>-<dev>
# (unique across projects, stable in both live and copy modes); else fall back.
if [ -n "${TS_HOSTNAME:-}" ]; then
  RAW_NAME="$TS_HOSTNAME"
elif [ -n "${DEVS_PROJECT_NAME:-}" ] && [ -n "${DEVCONTAINER_NAME:-}" ]; then
  RAW_NAME="${DEVS_PROJECT_NAME}-${DEVCONTAINER_NAME}"
else
  RAW_NAME="${WORKSPACE_FOLDER_NAME:-${DEVCONTAINER_NAME:-devcontainer}}"
fi
HOSTNAME_TS=$(printf '%s' "$RAW_NAME" | tr '[:upper:]' '[:lower:]' | tr -cd '[:alnum:]-')
HOSTNAME_TS="${HOSTNAME_TS:-devcontainer}"
# Namespace every devs node under a single `devs-` prefix so one `Host devs-*`
# block in ~/.ssh/config covers all repos with this devcontainer structure.
# Idempotent: strip any existing prefix first so we never get `devs-devs-`.
HOSTNAME_TS="devs-${HOSTNAME_TS#devs-}"
TAGS="${TS_TAGS:-tag:devcontainer}"

# Start the daemon (root, detached, idempotent) if not already up.
echo "🔌 Ensuring tailscaled is running (userspace networking, root)…"
sudo -n /usr/local/bin/start-tailscaled.sh

up_args=(--authkey="$TS_AUTHKEY" --hostname="$HOSTNAME_TS"
         --advertise-tags="$TAGS" --accept-dns=false --accept-routes=false)
[ -n "$SSH_ON" ] && up_args+=(--ssh)

echo "🔗 tailscale up as '$HOSTNAME_TS' (tags: $TAGS${SSH_ON:+, ssh})…"
if ! "${TS[@]}" up "${up_args[@]}"; then
  echo "⚠️  tailscale up failed — see /var/log/tailscaled.log. Container continues without Tailscale."
  exit 0
fi

dnsname=$("${TS[@]}" status --json 2>/dev/null | jq -r '.Self.DNSName // empty' | sed 's/\.$//')
echo "✅ On tailnet as: ${dnsname:-$HOSTNAME_TS}"
[ -n "$SSH_ON" ] && echo "🔑 Tailscale SSH on — connect with: ssh node@${dnsname:-$HOSTNAME_TS}"

# Optionally publish a port.
if [ -n "${TS_SERVE_PORT:-}" ]; then
  case "${TS_FUNNEL:-}" in
    1|true|yes)
      echo "🌐 funnel (PUBLIC internet) → :$TS_SERVE_PORT"
      "${TS[@]}" funnel --bg "$TS_SERVE_PORT" \
        || echo "⚠️  funnel failed (needs Funnel enabled + the funnel node attribute in ACL)"
      ;;
    *)
      echo "🔒 serve (tailnet only) → :$TS_SERVE_PORT"
      "${TS[@]}" serve --bg "$TS_SERVE_PORT" \
        || echo "⚠️  serve failed (needs HTTPS certificates enabled on the tailnet)"
      ;;
  esac
  "${TS[@]}" serve status 2>/dev/null || true
fi
exit 0
