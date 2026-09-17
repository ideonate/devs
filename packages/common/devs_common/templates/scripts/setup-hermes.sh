#!/bin/bash
# Seed Hermes Agent's default model into its persisted config (runs as the node user from
# post-start.sh on every container start).
#
# HERMES_HOME (/home/node/hermesconfig) is bind-mounted from ~/.devs/hermesconfig on the
# host, so config.yaml can't be baked into the image. Without a configured model Hermes
# falls back to its own pick, so write HERMES_DEFAULT_MODEL (a Dockerfile build arg) the
# first time — but never overwrite a model or provider the user has chosen since, e.g.
# with `hermes model`. HERMES_INFERENCE_MODEL still overrides per container at run time.
set -uo pipefail

HERMES=/home/node/.local/bin/hermes
[ -x "$HERMES" ] || exit 0
[ -n "${HERMES_DEFAULT_MODEL:-}" ] || exit 0

if [ -n "$("$HERMES" config get model.default 2>/dev/null)" ]; then
    exit 0
fi

if [ -z "$("$HERMES" config get model.provider 2>/dev/null)" ]; then
    "$HERMES" config set model.provider openrouter >/dev/null || exit 0
fi
"$HERMES" config set model.default "$HERMES_DEFAULT_MODEL" >/dev/null &&
    echo "✅ Hermes default model set to $HERMES_DEFAULT_MODEL in $HERMES_HOME/config.yaml"
