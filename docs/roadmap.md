# Roadmap

Estimates are guesses, not measurements. A usable two-user system is roughly
4–8 weekends of part-time work; a polished portal 2–3 months.

## Phase 0 – Manual proof (1–2 evenings)

- [ ] Create `eb-build` Arch VM on Proxmox (`infra/proxmox/`)
- [ ] Run `infra/build/setup-build-vm.sh`
- [ ] Build stock releng ISO by hand; build CachyOS desktop ISO from a pinned commit
- [ ] Confirm where the CachyOS profile keeps its package list and `pacman.conf`
      and adjust `render.py` if needed
- [ ] Flash with EtchDroid, boot on 2–3 different machines

## Phase 1 – CI builds from a profile (1 weekend)

- [x] `profile.yaml` schema and example profiles (Niklas, Emil)
- [x] `render.py` + tests
- [ ] Forgejo 15 LTS on `eb-portal`, mirror this repo, register runner on `eb-build`
- [ ] `.forgejo/workflows/build-iso.yml` builds changed users and uploads to the ISO store
- [ ] Pangolin public resources with SSO for git / iso

## Phase 2 – State sync (1–2 weekends)

- [ ] rest-server + Vaultwarden on `eb-state` (`infra/state/compose.yaml`)
- [ ] `ebox pull` for restic + chezmoi
- [ ] Pangolin machine client inside the ISO; first-boot enrolment
- [ ] Move per-user state (chezmoi source, aconfmgr config) into per-user repos `<user>/ebox-state`

## Phase 3 – Capture module (1–2 weekends)

- [ ] `ebox push` with aconfmgr, konsave / dconf
- [ ] PKGBUILD published to the own repo; `enrol.sh` one-liner

## Phase 4 – Portal (2–4 weekends)

- [ ] Profile form (base / desktop / keymap / packages) writing to Git
- [ ] Build status, download links
- [ ] Per-stick device list with revoke button
- [ ] Enrolment code flow

## Phase 5 – Hardening (ongoing)

- [ ] LUKS2 + FIDO2 persistence partition
- [ ] Secure Boot (sbctl UKI or shim + MOK)
- [ ] Mode B image snapshots via penguins-eggs `--crypted`
- [ ] Optional iPXE / archiso HTTP boot
