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
   - **Reusable** ✓ · **Ephemeral** ✓ (stopped containers auto-drop off the tailnet)
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
| `TS_AUTHKEY` | the `tskey-auth-…` key (required when enabled) | — |
| `TS_HOSTNAME` | tailnet node name → `<name>.<tailnet>.ts.net` | `<project>-<dev>` |
| `TS_TAGS` | advertised ACL tags | `tag:devcontainer` |
| `TS_SERVE_PORT` | local port to auto-publish over HTTPS | unset (none) |
| `TS_FUNNEL` | `1` ⇒ expose `TS_SERVE_PORT` to the **public internet** instead of tailnet-only | off |
| `TS_SSH` | `1` ⇒ accept Tailscale SSH into the container (see below) | off |

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

## Split-DNS / MagicDNS hostname resolution

Because containers join with `--accept-dns=false` (Tailscale never touches the system
resolver), tailnet *routing* works but **DNS doesn't** — split-DNS hostnames configured
on your tailnet (e.g. internal `*.example.com` zones, other nodes' `*.ts.net` names) fail
to resolve even though their IPs are reachable. Symptom:

```
$ curl http://internal-app.example.com:9000/
curl: (6) Could not resolve host: internal-app.example.com
```

The fix is wired into the template: `scripts/post-start.sh` (a `postStartCommand`
orchestrator, gated on `TS_ENABLE`) calls the root helper `sudo-scripts/setup-magicdns.sh`,
which **prepends the MagicDNS resolver `100.100.100.100` to `/etc/resolv.conf`** as the
first nameserver, leaving the ISP/host nameservers below it.

- It runs on **every start** (not `postCreate`) because Docker regenerates
  `/etc/resolv.conf` each time the container starts.
- MagicDNS answers the split-DNS + `ts.net` zones authoritatively; for any other name it
  returns **SERVFAIL**, and glibc falls through to the next nameserver — so public DNS
  (github.com, pip, npm, …) keeps working. This SERVFAIL-vs-NXDOMAIN behaviour is why
  *prepend* is safe and why we do **not** use `--accept-dns=true` (which would make
  MagicDNS SERVFAIL every non-tailnet name with no upstream to fall back to).
- It's a no-op unless `tailscaled` is up, and idempotent (won't double-prepend).

Tailnet-wide **Split DNS Routes** are an admin-console setting (DNS page), not something
the container configures — `tailscale dns status` should list them.

**Verify** (after a rebuild, since the sudoers entry is generated at image build):
```bash
getent hosts internal-app.example.com      # resolves to a 100.x tailnet IP
cat /etc/resolv.conf                        # 100.100.100.100 first, ISP servers below
getent hosts github.com                     # public DNS still works (SERVFAIL fallthrough)
```

To unblock an already-running container before rebuilding (ephemeral — gone on next start):
```bash
sudo sed -i '1i nameserver 100.100.100.100' /etc/resolv.conf
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
