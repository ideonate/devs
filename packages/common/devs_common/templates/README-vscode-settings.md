# VS Code settings in this template

`machine-settings.json` is baked into the image at
`~/.vscode-server/data/Machine/settings.json` (see the Dockerfile), **not** put in
`devcontainer.json` under `customizations.vscode.settings`.

Why: that `customizations` block is applied by the **Dev Containers extension only**. A
Remote-SSH connection — which is how you reach a container over Tailscale SSH — never reads
`devcontainer.json`, so it got neither settings nor extensions. Machine settings cover both
paths. For the same reason the `ideonate.*` extensions are unzipped into the image and
registered via `register-vscode-extensions.js`.

**Don't add a `settings` block back to `devcontainer.json`**: the Dev Containers extension
writes it over the same machine-settings file, and the two would silently drift.

## tmux (opt-in, off by default)

`machine-settings.json` *defines* a `tmux` terminal profile and the
`ideonate.vscode-tmux-auto-reattach` settings, but leaves the default profile as `zsh` and
`tmuxAutoReattach.runOnStartup` as `false`. Nothing changes unless you ask for it.

To turn it on, set `DEVS_TMUX=1` — via `DEVS.yml` `env_vars:`, `devs start … --env
DEVS_TMUX=1`, or a mounted `~/.devs/envs/<project>/.env`. On each container start,
`scripts/setup-vscode-settings.sh` merges `machine-settings.tmux.json` over the base file,
which flips the default profile to tmux and enables auto-reattach. Unset it and the next
start reverts to the base file — no rebuild needed either way.

You can still open a tmux terminal manually from the profile dropdown with `DEVS_TMUX`
unset; the profile is always defined.

### Notes on the tmux settings

- The profile's args are a bare `new-session` — deliberately **not** `new-session -A -s
  <name>`. The `-A` form attaches to the named session if it exists, so every "New
  Terminal" lands you back in the *same* session instead of opening a new one. Reattaching
  to existing sessions is the auto-reattach extension's job, not the profile's.
- `~/.tmux.conf` (written in the Dockerfile) sets `mouse on`, 50k scrollback, and
  `set-titles` so tab titles show the running command. Existing sessions keep their old
  config — `tmux source-file ~/.tmux.conf` then start a new session, or `tmux kill-server`.
- With `mouse on`, click-drag and double-click go to tmux rather than VS Code.
  `terminal.integrated.macOptionClickForcesSelection` (on in the base file) lets
  Option-click/drag bypass tmux for native selection. `prefix + m` toggles mouse mode.
- `tmuxAutoReattach.shellPath=/bin/sh` runs the reattach as the terminal's own process.
  Without it the terminal starts the default profile (`tmux new-session`) first and the
  attach nests inside that tmux.
- `terminal.integrated.enablePersistentSessions: false` (tmux overlay) stops VS Code
  reviving old terminal tabs on reload — each would launch the default profile before the
  extension can reattach, again causing nested tmux.
