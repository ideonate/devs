#!/bin/bash
set -euo pipefail

runner="$(cd "$(dirname "$0")/.." && pwd)/devs_common/templates/scripts/run-autoexec.sh"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

mkdir -p "$tmp/hooks"
printf '#!/bin/sh\necho first >> "$AUTOEXEC_RESULT"\n' > "$tmp/hooks/10-first.sh"
printf '#!/bin/sh\necho failed >> "$AUTOEXEC_RESULT"; exit 7\n' > "$tmp/hooks/20-fails.sh"
printf '#!/bin/sh\necho last >> "$AUTOEXEC_RESULT"\n' > "$tmp/hooks/30-last.sh"
printf '#!/bin/sh\necho skipped >> "$AUTOEXEC_RESULT"\n' > "$tmp/hooks/40-disabled.sh"
chmod +x "$tmp/hooks/10-first.sh" "$tmp/hooks/20-fails.sh" "$tmp/hooks/30-last.sh"

export AUTOEXEC_RESULT="$tmp/result"
if DEVS_AUTOEXEC_DIR="$tmp/hooks" "$runner"; then
  echo "expected a non-zero status when a hook fails" >&2
  exit 1
fi

expected="$(printf 'first\nfailed\nlast')"
[ "$(cat "$AUTOEXEC_RESULT")" = "$expected" ] || {
  echo "hooks did not run in order, continue after failure, or skip non-executables" >&2
  exit 1
}

DEVS_AUTOEXEC_DIR="$tmp/missing" "$runner"
echo "run-autoexec tests passed"
