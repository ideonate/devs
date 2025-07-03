#!/bin/bash
# Automatic Python virtual environment activation for zsh

# Automatic Python virtual environment activation
function auto_venv() {
  if [[ -n "$VIRTUAL_ENV" ]]; then
    if [[ ! "$PWD" == "$VIRTUAL_ENV_PROJECT"* ]]; then
      deactivate
      unset VIRTUAL_ENV_PROJECT
    fi
  fi
  local current_dir="$PWD"
  while [[ "$current_dir" != "/" ]]; do
    if [[ -f "$current_dir/venv/bin/activate" && -f "$current_dir/requirements.txt" ]]; then
      if [[ "$VIRTUAL_ENV" != "$current_dir/venv" ]]; then
        source "$current_dir/venv/bin/activate"
        export VIRTUAL_ENV_PROJECT="$current_dir"
        echo "🐍 Activated venv: $current_dir/venv"
      fi
      break
    fi
    current_dir=$(dirname "$current_dir")
  done
}

# Hook into cd command
function cd() {
  builtin cd "$@"
  auto_venv
}

# Run auto_venv on shell startup
auto_venv