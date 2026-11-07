#!/usr/bin/env bash
# Create the echobox-go guests on a Proxmox VE node. Prints the commands by
# default; run with --apply on the Proxmox host to execute them.
#
#   infra/proxmox/create-guests.sh            # dry run
#   infra/proxmox/create-guests.sh --apply
#
# Override any variable from the environment, e.g. STORAGE=fast BRIDGE=vmbr1.

set -euo pipefail

STORAGE="${STORAGE:-local-lvm}"
BRIDGE="${BRIDGE:-vmbr0}"
# LXC template, e.g. from `pveam available --section system`; download with pveam first.
LXC_TEMPLATE="${LXC_TEMPLATE:-local:vztmpl/debian-13-standard_amd64.tar.zst}"
# Arch ISO uploaded to the node, used to install eb-build by hand.
ARCH_ISO="${ARCH_ISO:-local:iso/archlinux-x86_64.iso}"
ID_BUILD="${ID_BUILD:-210}" ID_PORTAL="${ID_PORTAL:-211}" ID_STATE="${ID_STATE:-212}" ID_EDGE="${ID_EDGE:-213}"

apply=0
[[ "${1:-}" == "--apply" ]] && apply=1

run() {
    printf '+ %s\n' "$*"
    if (( apply )); then "$@"; fi
}

# eb-build: full VM, mkarchiso needs real root, loop devices and bind mounts.
run qm create "$ID_BUILD" --name eb-build --ostype l26 --cpu host --cores 8 --memory 24576 \
    --scsihw virtio-scsi-single --scsi0 "$STORAGE:150,iothread=1,discard=on" \
    --net0 "virtio,bridge=$BRIDGE" --ide2 "$ARCH_ISO,media=cdrom" --boot "order=scsi0;ide2" \
    --bios ovmf --efidisk0 "$STORAGE:1,efitype=4m,pre-enrolled-keys=0" --agent enabled=1

# Unprivileged containers for everything that is not the build.
lxc() {
    local id="$1" name="$2" cores="$3" mem="$4" disk="$5"
    run pct create "$id" "$LXC_TEMPLATE" --hostname "$name" --cores "$cores" --memory "$mem" \
        --rootfs "$STORAGE:$disk" --net0 "name=eth0,bridge=$BRIDGE,ip=dhcp" \
        --unprivileged 1 --features nesting=1 --onboot 1
}
lxc "$ID_PORTAL" eb-portal 2 4096 32     # Forgejo, portal, ISO store (grow for many ISOs)
lxc "$ID_STATE"  eb-state  2 2048 16     # add a large mount point for /srv/restic
lxc "$ID_EDGE"   eb-edge   1 512  4      # Newt

(( apply )) || echo "(dry run; re-run with --apply on the Proxmox host)"
