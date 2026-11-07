#!/usr/bin/env bash
# Prepare the eb-build VM (Arch Linux). Run as root once after installing Arch.
#
#   CACHYOS_ISO_REF=<commit> infra/build/setup-build-vm.sh
#
# Then register the Forgejo runner (printed at the end).

set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "run as root" >&2; exit 1; }

CACHYOS_ISO_REPO="${CACHYOS_ISO_REPO:-https://github.com/CachyOS/CachyOS-Live-ISO.git}"
CACHYOS_ISO_REF="${CACHYOS_ISO_REF:?pin a tested CachyOS-Live-ISO commit}"
RUNNER_USER="${RUNNER_USER:-runner}"

pacman -Syu --needed --noconfirm archiso git rsync openssh python python-yaml python-jsonschema \
    base-devel devtools sudo
# forgejo-runner: use the distro package if available, otherwise the release binary
# from https://code.forgejo.org/forgejo/runner/releases.
pacman -S --needed --noconfirm forgejo-runner || echo "!! install forgejo-runner manually"

id "$RUNNER_USER" >/dev/null 2>&1 || useradd -m -s /bin/bash "$RUNNER_USER"
# The runner may run mkarchiso as root and nothing else. A profile can still put
# anything into the image, so only let this runner build protected branches.
cat > /etc/sudoers.d/20-ebox-runner <<SUDO
Defaults:$RUNNER_USER env_keep += "SOURCE_DATE_EPOCH"
$RUNNER_USER ALL=(root) NOPASSWD: /usr/bin/mkarchiso
SUDO
chmod 440 /etc/sudoers.d/20-ebox-runner
visudo -cf /etc/sudoers.d/20-ebox-runner

# Pinned CachyOS ISO profile.
install -d /opt/cachyos-live-iso
if [[ ! -d /opt/cachyos-live-iso/.git ]]; then
    git clone "$CACHYOS_ISO_REPO" /opt/cachyos-live-iso
fi
git -C /opt/cachyos-live-iso fetch --quiet origin
git -C /opt/cachyos-live-iso checkout --quiet "$CACHYOS_ISO_REF"

cat <<NEXT

Next steps
  1. Find the archiso profile inside /opt/cachyos-live-iso (roadmap phase 0) and
     set CACHYOS_PROFILE_DIR to it in the runner's environment.
  2. Register the runner with label eb-build:
       sudo -u $RUNNER_USER forgejo-runner register \\
         --instance https://git.example.org --labels eb-build:host --name eb-build
  3. Optional: pacoloco cache and the [echobox] repo (see infra/build/README.md).
NEXT
