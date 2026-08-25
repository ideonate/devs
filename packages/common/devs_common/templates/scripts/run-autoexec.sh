#!/bin/bash
# Run optional, user-supplied startup hooks from the mounted devs environment.
# The directory's presence is the opt-in; hooks run in lexical filename order.
set -uo pipefail

hooks_dir="${DEVS_AUTOEXEC_DIR:-/home/node/.devs-env/autoexec}"
[ -d "$hooks_dir" ] || exit 0

status=0
found=0
for hook in "$hooks_dir"/*; do
  [ -f "$hook" ] || continue
  [ -x "$hook" ] || {
    echo "ℹ️  Skipping non-executable autoexec hook: $(basename "$hook")"
    continue
  }

  found=1
  echo "📋 Running autoexec hook: $(basename "$hook")"
  if "$hook"; then
    echo "✅ Autoexec hook completed: $(basename "$hook")"
  else
    hook_status=$?
    echo "⚠️  Autoexec hook failed ($hook_status): $(basename "$hook")"
    status=1
  fi
done

[ "$found" -eq 0 ] || echo "🏁 Autoexec hooks finished"
exit "$status"
