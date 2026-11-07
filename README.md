<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/echobox-go/.github/main/profile/assets/mark-dark.svg">
    <img src="https://raw.githubusercontent.com/echobox-go/.github/main/profile/assets/mark-light.svg" alt="echobox-go" width="96">
  </picture>
</p>

<h1 align="center">builder</h1>

<p align="center"><b>Turns a user profile into an echobox-go live ISO.</b></p>

---

Each user has a `profiles/users/<user>/profile.yaml` (base distro, desktop,
keymap, packages). On a push, the Forgejo runner on the `eb-build` VM renders it
into an archiso profile and builds the ISO with `mkarchiso`. The ISO carries
**no secrets**: credentials come from `ebox enrol` when the stick first boots.

This repo also holds the system design ([docs/](docs/architecture.md)) and the
deployment for the whole stack ([infra/](infra/)).

```
 profile.yaml ──► render.py ──► archiso profile ──► mkarchiso ──► echobox-go-<user>.iso
                     ▲
              ../ebox (CLI + units copied into the image)
```

## Use

```sh
# clone side by side
git clone https://github.com/echobox-go/ebox    ~/echobox-go/ebox
git clone https://github.com/echobox-go/builder ~/echobox-go/builder

make test                          # schema checks, renderer tests, shellcheck
make render PROFILE=emil           # render against a test fixture into build/emil/profile
./build-iso.sh --user niklas       # on eb-build: render + mkarchiso (mkarchiso via sudo)
```

## What `render.py` changes

| Step | Result in the profile |
|---|---|
| Packages | `ebox` dependencies, shell, desktop set (`desktops.yaml`), user packages appended to `packages*.x86_64`, de-duplicated |
| CPU level | for CachyOS `generic`, `-v3`/`-v4`/`-znver4` repos removed from `pacman.conf` |
| AUR | `[echobox]` repo added first in `pacman.conf` when `--repo-url` is given; without it, profile `aur:` is an error |
| Keyboard | `vconsole.conf` + `xorg.conf.d/00-keyboard.conf` from `keymaps.yaml` |
| System | `hostname`, `locale.conf` (+ `glibc-locales`), `localtime` |
| Desktop | `display-manager.service`, `graphical.target`, NetworkManager instead of releng's iwd/networkd, autologin for the live user |
| ebox | `/usr/local/bin/ebox`, units, `/etc/ebox/ebox.conf` (public values only) |
| Brand | boot menu titles, `/etc/motd`, `/usr/share/pixmaps/echobox-go.svg`, `iso_name=echobox-go-<user>` |

Base profiles: archiso's `releng` for `base: arch`; a pinned
`CachyOS/CachyOS-Live-ISO` checkout for `base: cachyos` (`CACHYOS_PROFILE_DIR`).
Tests use stand-ins from `tests/fixtures.py`; checking against the real CachyOS
profile is roadmap phase 0.

## Layout

| Path | What |
|---|---|
| `render.py`, `build-iso.sh`, `keymaps.yaml`, `desktops.yaml` | The builder |
| `profiles/` | Per-user profiles and `schema/profile.schema.json` (the portal keeps a copy) |
| `.forgejo/workflows/build-iso.yml` | ISO pipeline on the self-hosted runner |
| `docs/` | [Architecture](docs/architecture.md), [roadmap](docs/roadmap.md) |
| `infra/` | Proxmox guests, compose files for state / portal / edge, build VM setup, Pangolin resources |

Part of [echobox-go](https://github.com/echobox-go): [`ebox`](https://github.com/echobox-go/ebox) · `builder` · [`portal`](https://github.com/echobox-go/portal)

<sub>echobox-go is an independent project and is not affiliated with Arch Linux or CachyOS.</sub>
