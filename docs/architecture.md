# Architecture

Design record for echobox-go, based on the research done in November 2026
("Live Linux USB self-hosted sync"). Version numbers and project status below
were checked then; re-check before pinning.

## Goal

- Each user has their own live OS: Niklas on CachyOS + Plasma, Emil on plain
  Arch + Dvorak + a desktop of his choice.
- A user can capture ("sync up") their environment from a running machine at
  any time.
- The server builds a per-user live ISO that can be written to a USB stick,
  including from an Android phone.
- Booting the stick on any computer and getting online pulls the latest
  environment, logins and files ("sync down").

No existing open source project does the whole flow, so echobox-go glues
together proven parts.

## Repositories

| Repo | Holds |
|---|---|
| [`ebox`](https://github.com/echobox-go/ebox) | The CLI, systemd units, PKGBUILD, enrol script |
| [`builder`](https://github.com/echobox-go/builder) | Renderer, ISO build, user profiles + schema, build workflow, these docs, `infra/` |
| [`portal`](https://github.com/echobox-go/portal) | Web app (with a copy of the profile schema) |
| [`.github`](https://github.com/echobox-go/.github) | Organisation profile and the master brand files |

Clone them side by side (`~/echobox-go/{ebox,builder,portal}`): the builder
copies `../ebox` into each ISO, and the portal's compose file builds `../portal`.

## Building blocks

| Layer | Choice | Notes |
|---|---|---|
| Build engine | `mkarchiso` (archiso `releng`) for Arch; pinned checkout of `CachyOS/CachyOS-Live-ISO` for CachyOS | Needs real root, loop devices and bind mounts → full VM, not unprivileged LXC |
| Build queue | Forgejo Actions (Forgejo 15 LTS, forgejo-runner) on `eb-build` | Triggered by pushes to `profiles/users/**` |
| Profile | `profiles/users/<user>/profile.yaml`, validated by `profiles/schema/profile.schema.json` | Rendered into an archiso profile by `render.py` (builder repo) |
| Push / pull | `ebox` CLI wrapping aconfmgr, chezmoi, konsave / dconf, restic | Ships as a pacman package plus a one-line enrol script |
| Home data | restic `rest-server` (`--private-repos --append-only`) | Client-side encryption; a stolen stick cannot delete history |
| Secrets | Vaultwarden + `bw` CLI | Never baked into ISOs |
| Network to server | One Pangolin machine client per stick (Newt site connector on `eb-edge`) | Revoke the client to cut off a lost stick |
| Package cache | pacoloco + own repo for AUR builds (aurutils) | On `eb-build` |
| Portal | Small FastAPI + htmx app behind Pangolin SSO | Reads identity from Pangolin's `Remote-User` header |
| USB writing | `dd` / Ventoy on PC, EtchDroid on Android (no root) | iPhone: only copying the ISO onto an existing Ventoy stick |
| Optional image snapshot | penguins-eggs `remaster --crypted` | "Mode B"; never plain `--clone` for anything downloadable |

## Proxmox guests

| Guest | Type | Suggested size | Runs |
|---|---|---|---|
| `eb-build` | VM (Arch) | 8 vCPU, 16–32 GB RAM, 150 GB disk | forgejo-runner, archiso, pinned CachyOS-Live-ISO, pacoloco, aurutils repo, optional sbctl |
| `eb-portal` | LXC | 2 vCPU, 2–4 GB | Forgejo 15 LTS, portal app, ISO download store |
| `eb-state` | LXC | 2 vCPU, 2 GB + large storage | restic rest-server, Vaultwarden |
| `eb-edge` | LXC | 1 vCPU, 512 MB | Newt site connector to Pangolin |

The build VM must not be able to reach `eb-state`: it only needs Git, the
package mirrors and the ISO store.

## Pangolin resources

- **Public, behind SSO (browser):** `portal.<domain>`, `git.<domain>`,
  `iso.<domain>` (so a phone can download after logging in).
- **Private, machine clients only:** rest-server, Vaultwarden, pacoloco, the
  portal's agent API (`/api/agent/*`).
- Give each stick a direct grant on the private resources it needs (role
  assignment for machine clients is edition-dependent).

## Profile

```yaml
user: niklas
base: cachyos            # cachyos | arch
cpu_level: generic       # generic | v3 | v4 — generic for sticks that roam
desktop: plasma          # plasma | gnome | hyprland | xfce | none
keymap: se               # name from keymaps.yaml (builder repo), or an object
locale: sv_SE.UTF-8
timezone: Europe/Stockholm
packages: [firefox, neovim]
aur: []                  # prebuilt into the echobox repo by aurutils
persistence: luks-passphrase   # none | luks-passphrase | luks-fido2
sync:
  home_paths: [Documents, .ssh]   # restored by restic
  dotfiles: true                  # chezmoi
  desktop_settings: true          # konsave / dconf
```

Rendering (`render.py` (builder repo)):

1. Copy the base archiso profile (releng or the pinned CachyOS one).
2. Append desktop and user packages to the packages list.
3. For `cpu_level: generic`, strip `-v3`/`-v4`/`-znver4` repos from
   `pacman.conf` so the stick boots on old CPUs.
4. Write keymap (`vconsole.conf` + X11/Wayland layout), locale, timezone,
   hostname.
5. Enable the display manager and graphical target.
6. Add `ebox`, its config (`/etc/ebox/ebox.conf`, public
   values only) and boot units.
7. Set `iso_name`, `iso_label` and file permissions in `profiledef.sh`.

## The `ebox` CLI

| Command | Does |
|---|---|
| `ebox enrol` | Pairs the device with the portal using a one-time code; stores this stick's Pangolin client and restic credential on the encrypted persistence partition |
| `ebox push` | `aconfmgr save`, `chezmoi re-add` + commit, konsave / dconf export, `restic backup` of the chosen home paths, push to the user's repo (profile changes trigger a rebuild) |
| `ebox pull` | On live boot after `network-online.target`: `restic restore`, `chezmoi apply`, `aconfmgr apply` for packages not in the ISO, konsave / dconf import |
| `ebox build` | Asks the portal to rebuild the user's ISO and reports the status |
| `ebox status` | Shows enrolment, tunnel, last push / pull |
| `ebox push --image` | Optional mode B: penguins-eggs encrypted remaster + upload |

Units: `ebox-liveuser.service` (creates the live user before the display
manager), `ebox-pull.service` (runs `pull` on boot once enrolled),
`ebox-push.timer` (optional periodic push).

The CLI is a Bash script for now because it mostly drives other tools. A Go
rewrite (single static binary, matches the `-go` name) is an option once the
commands settle.

## User journey

1. Sign in to the portal (Pangolin SSO) from phone or PC.
2. Pick base / desktop / keymap in the form, **or** run `ebox enrol` and
   `ebox push` on an already configured machine.
3. The portal commits the profile; Forgejo Actions builds the ISO on
   `eb-build` (roughly 30–60 min for CachyOS, a few GB).
4. Download from `iso.<domain>`.
5. Write the stick (EtchDroid on Android, `dd` / Ventoy on PC).
6. First boot anywhere: Wi-Fi, then the one-time enrolment code; a LUKS2
   persistence partition is created in the free space and holds the
   credentials.
7. `ebox pull` restores the environment. Later boots only need the LUKS
   unlock.
8. `ebox push` whenever. Home changes are just a new restic snapshot; only
   profile changes cause a rebuild.
9. Lost stick: revoke its Pangolin client and restic credential in the portal.

## Security model

- ISOs carry only public configuration; credentials come from enrolment.
- One Pangolin client and one restic credential per stick.
- Unlock with passphrase; FIDO2 via `systemd-cryptenroll` where available.
- rest-server in append-only mode.
- The portal only trusts `Remote-User` when the request also carries the
  shared header Pangolin injects for this resource (`X-Ebox-Proxy-Token`),
  so it cannot be spoofed by anything that bypasses Pangolin.

## Caveats

- **CachyOS CPU levels:** v3/v4 builds fail on older CPUs; Intel 12th gen+ that
  report v4 should be treated as v3. Default to `generic`.
- **Secure Boot:** stock archiso does not boot with it on. Sign your own UKI
  (sbctl), use shim + MOK, or tell users to disable it.
- **Wi-Fi before sync:** every ISO needs `linux-firmware` and NetworkManager.
- **RAM:** live desktop runs from RAM + overlay; 8 GB+ advised.
- **Trademarks:** ship ISOs under the echobox-go name and artwork (org `brand/`),
  not as "Arch Linux" or "CachyOS".
- **penguins-eggs** versioning is inconsistent across release pages; pin a
  tested version.
- **Phone:** building ISOs on a phone is not realistic (no real root/loop
  devices, x86_64 emulation). The phone is the remote control and USB writer.
