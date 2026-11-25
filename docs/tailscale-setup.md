# Tailscale Support in Devcontainers

Each devcontainer can join your tailnet as **its own node** and publish a local port over
HTTPS — reach a container's dev server from your laptop/iPad/phone, on LAN or remotely, with
no SSH tunnels and no port forwarding, and optionally SSH straight into the container. Built
into the devs template (`Dockerfile`, `scripts/start-tailscale.sh`, `scripts/ts.sh`, and the
root helpers `sudo-scripts/start-tailscaled.sh` + `sudo-scripts/ts-cli.sh`); if you're adapting
a custom devcontainer, copy those and add the `start-tailscale.sh` step to your
`post-create-wrapper.sh`.

`tailscaled` runs in **userspace-networking** mode (no TUN device, no clash with a host
tailscaled) **as root**, via the same NOPASSWD `sudo-scripts` pattern as `init-firewall.sh`.
Root is what lets **Tailscale SSH** open login sessions; userspace networking is what avoids
needing a `/dev/net/tun` device. The node user drives it through `ts` (→ `sudo ts-cli.sh`).

Naming: nodes register as **`<project>-<dev>`** (e.g. `myorg-myapp-alice`) — the dev
name alone isn't unique across projects. Override with `TS_HOSTNAME`.

## Strictly opt-in

The startup step is **off by default** — it exits cleanly unless `TS_ENABLE=1`. A container with
no Tailscale config is unaffected (just a skipped-step line in the log). An auth key alone does
**not** turn it on, so the key can sit in your shared env file harmlessly until a project opts in.

## One-time tailnet setup (admin console)

Do these once, **in order** (the key dialog won't offer the tag until the ACL is saved):

1. **Define the tag** — Access Controls (https://login.tailscale.com/admin/acls). Add a top-level
   `tagOwners` block (merge with any existing one):
   ```jsonc
   "tagOwners": {
     "tag:devcontainer": ["autogroup:admin"],
   },
   ```
2. **Enable HTTPS + MagicDNS** for the tailnet (DNS page) — required for `tailscale serve`.
3. **Generate an auth key** — Settings → Keys → **Generate auth key** (the *Auth keys* section,
   **not** *API access tokens*):
   - **Reusable** ✓ · **Ephemeral** ✗ — a non-ephemeral node survives disconnects, which is
     what `TS_AUTHKEY` wants (see Configuration below). Mint a second, *ephemeral* key for
     `TS_AUTHKEY_EPHEMERAL` if you also want throwaway nodes that auto-drop off the tailnet.
   - **Tags:** `tag:devcontainer`
   - Copy the **`tskey-auth-…`** value (shown once).

   ⚠ It must be a device **auth key** (`tskey-auth-…`). An API access token (`tskey-api-…`) or
   admin OAuth secret fails `tailscale up` with *"key cannot be used for node auth …
   CONTROL_API_SCOPE_ALL"*. (An OAuth client secret works only if created with the
   Auth Keys → Write scope + a tag.)

## Configuration

| Var | Purpose | Default |
|-----|---------|---------|
| `TS_ENABLE` | master switch, opt-in (`1`/`true`/`yes`) | off |
| `TS_AUTHKEY` | preferred `tskey-auth-…` key: reusable, tagged, **non-ephemeral** | — |
| `TS_AUTHKEY_EPHEMERAL` | fallback key used only when `TS_AUTHKEY` is unset: reusable, tagged, **ephemeral** | — |
| `TS_HOSTNAME` | tailnet node name → `<name>.<tailnet>.ts.net` | `<project>-<dev>` |
| `TS_TAGS` | advertised ACL tags | `tag:devcontainer` |
| `TS_SERVE_PORT` | local port to auto-publish over HTTPS | unset (none) |
| `TS_FUNNEL` | `1` ⇒ expose `TS_SERVE_PORT` to the **public internet** instead of tailnet-only | off |
| `TS_SSH` | `1` ⇒ accept Tailscale SSH into the container (see below) | off |

Prefer a **non-ephemeral** key. An ephemeral node is garbage-collected by the control plane
shortly after it disconnects; if that happens while the container keeps running, `tailscaled`
wedges retrying a dead node key (*"PollNetMap: initial fetch failed 404: node not found"*)
until the next bring-up. `TS_AUTHKEY_EPHEMERAL` exists for the throwaway case — a natural
home is the shared `default/.env` so any container still joins the tailnet without a
per-project stable key. With neither set (and `TS_ENABLE=1`), the bring-up warns and no-ops.

The container's `/var/lib/tailscale` is a named volume (`<workspace>-tailscale-state`), so the
node keeps one identity and 100.x address across rebuilds — a saved VS Code SSH host stays
valid. Note `devs clean` logs the node out but does not delete that volume.

**Where to put them** (devs reads both; split by secrecy):

- **Secret (`TS_AUTHKEY`)** → `~/.devs/envs/<org-repo>/.env`, mounted into the container.
  ⚠ devs uses the **project dir only if it exists, else `~/.devs/envs/default/.env`** — it does
  *not* merge them. Easiest: keep the key in `default/.env` (inert until a project sets
  `TS_ENABLE=1`); if a project-specific env dir exists, the key must live **there**.
- **Non-secret switches** → repo `DEVS.yml` `env_vars:` or `devs start … --env`. Never commit the
  key in `DEVS.yml`.

Example — key once in `~/.devs/envs/default/.env`, then per project:
```yaml
# DEVS.yml
env_vars:
  TS_ENABLE: "1"
  TS_SERVE_PORT: "5173"
```
or ad hoc: `devs start sally --env TS_ENABLE=1 --env TS_SERVE_PORT=5173`.

Changing the envs folder triggers a rebuild, so new vars are picked up. `serve`/`funnel` are
auto-applied only at create — recreate, or re-run the commands below, after a stop/start.

## Usage inside the container

`TS_SERVE_PORT` just runs `serve` for you at startup; you can also do it by hand. `ts` is a
wrapper around `tailscale` pointed at this container's daemon socket:

```bash
ts status                 # node name, tailnet IP, serve config
ts serve --bg 5173        # publish localhost:5173 over HTTPS (tailnet only)
ts serve status           # show the resulting https://<name>.<tailnet>.ts.net URL
ts funnel --bg 5173       # publish publicly (needs the funnel node-attr in ACL)
ts serve --https=443 off  # stop serving
```

## SSH straight into the container (`TS_SSH=1`)

With `TS_SSH=1`, the container accepts **Tailscale SSH** — connect from any tailnet device with
no keys and no `sshd`; auth is by your tailnet identity (ACL). This also lets **VS Code
Remote-SSH** target the container directly (`<project>-<dev>.<tailnet>.ts.net`) instead of going
via the host + docker attach.

Two things to set up:

1. **Env:** `TS_SSH=1` (alongside `TS_ENABLE=1`) in `DEVS.yml` / `.env` / `--env`.
2. **ACL `ssh` rule** (Access Controls) — allow your devices to log in as `node` on tagged
   containers:
   ```jsonc
   "ssh": [
     {
       "action": "accept",
       "src":    ["autogroup:member"],
       "dst":    ["tag:devcontainer"],
       "users":  ["node"],
     },
   ],
   ```

Then from any tailnet device:
```bash
ssh node@<project>-<dev>.<tailnet>.ts.net      # e.g. ssh node@myorg-myapp-alice...
```
or add a `Host` entry (`HostName …ts.net`, `User node`) and point VS Code Remote-SSH at it.

## DNS: stone-dns, not MagicDNS

Because containers join with `--accept-dns=false`, Tailscale never touches the
container's resolver. DNS comes from **stone-dns on the docker host** instead: the
template's `devcontainer.json` passes

```jsonc
"--add-host=host.docker.internal:host-gateway",  // the stone-ingress API on :8800
"--dns=172.17.0.1",   // stone-dns: every *.internal + split-DNS zones + ts.net + public
"--dns=1.1.1.1"       // fallback: stone-dns down => no dev domains, never no DNS
```

so split-DNS and `*.internal` names (e.g. `cairn.internal`) resolve whether or not the
in-container `tailscaled` is up. This replaces the old approach of prepending the
MagicDNS resolver `100.100.100.100` to `/etc/resolv.conf` (`setup-magicdns.sh`, now
removed), which silently did nothing when Tailscale wasn't up. See stone-ingress
`docs/adding-a-service.md` step 4.

The `*.internal` services use HTTPS certs from stone-caddy's internal CA, so
`post-start.sh` also runs `sudo-scripts/trust-stone-ca.sh` on every start (before the
`TS_ENABLE` gate) to install that root into the system store (which curl and Claude Code
use) and Chromium's NSS store. Off stone-pc the script skips quietly.

**Verify** (after a rebuild — `--dns` and the sudoers entry are fixed at container
create / image build):
```bash
getent hosts cairn.internal                 # 100.83.126.31
getent hosts github.com                     # public DNS still works
echo | openssl s_client -connect cairn.internal:443 -servername cairn.internal 2>/dev/null \
  | grep "Verify return"                    # Verify return code: 0 (ok)
```

## Notes & troubleshooting

- **Funnel is off by default** and double-gated: only fires with `TS_FUNNEL=1` *and* a `funnel`
  `nodeAttrs` grant in the ACL; otherwise it stays tailnet-only.
- **Ephemeral identity** is the default — fine for throwaway containers; hostname is stable while
  running. For a long-lived node, mount a volume at `/var/lib/tailscale`.
- **Logs:** `/var/log/tailscaled.log` inside the container.
- **`tailscaled` runs as root** via the NOPASSWD `sudo-scripts` (like `init-firewall.sh`); the
  `node` user reaches it through `ts` → `sudo ts-cli.sh`. Userspace networking still means no TUN
  device is required.
- **`key cannot be used for node auth`** → wrong credential type; generate a `tskey-auth-…` key
  (see above), not an API token.
- **`requested tags … are invalid or not permitted`** → the `tagOwners` ACL (step 1) is missing
  the tag, or the key wasn't created with it. To test untagged, set `TS_TAGS=""`.
- The Tailscale binaries are baked into the image (small, inert if unused), like the VS Code CLI
  and `cloudflared` — only the runtime is gated by `TS_ENABLE`.
