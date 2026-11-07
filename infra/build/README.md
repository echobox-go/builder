# eb-build VM

Arch Linux VM that builds the ISOs. `mkarchiso` needs real root, loop devices
and bind mounts, so this is a VM, not an LXC.

1. Create the VM (`infra/proxmox/create-guests.sh`) and install Arch.
2. `CACHYOS_ISO_REF=<commit> infra/build/setup-build-vm.sh`
3. Register forgejo-runner with the label `eb-build` (printed by the script).
4. Give the runner an SSH key that can only `rsync` into `/srv/iso` on
   `eb-portal`, and store it as the Forgejo secret `ISO_UPLOAD_KEY`.

## echobox pacman repo (AUR builds)

Needed for `aur:` packages and for `aconfmgr-git` / `konsave` inside the ISOs.

- Build with aurutils into `/srv/repo/echobox` and sign with a dedicated key.
- `pacman-key --lsign-key <fingerprint>` on this VM so mkarchiso trusts it.
- Serve `/srv/repo` over HTTP and pass `EBOX_REPO_URL=http://eb-build/repo/echobox/$arch`
  to the build.

## pacoloco

Optional pacman cache so repeated builds don't re-download every package.
Point the base profiles' mirrorlists at it once it runs.
