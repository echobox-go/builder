"""Minimal stand-ins for archiso base profiles, for tests and local `make render`.

    python3 tests/fixtures.py releng build/fixture-releng
    python3 tests/fixtures.py cachyos build/fixture-cachyos
    python3 tests/fixtures.py ebox build/fixture-ebox      # stand-in for the ebox repo

They mimic the shape of archiso's releng profile and of a CachyOS profile; they
are not buildable ISOs.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

PROFILEDEF = """#!/usr/bin/env bash
# shellcheck disable=SC2034
iso_name="archlinux"
iso_label="ARCH_$(date --date="@${SOURCE_DATE_EPOCH:-$(date +%s)}" +%Y%m)"
iso_publisher="Arch Linux <https://archlinux.org>"
iso_application="Arch Linux Live/Rescue DVD"
iso_version="$(date --date="@${SOURCE_DATE_EPOCH:-$(date +%s)}" +%Y.%m.%d)"
install_dir="arch"
buildmodes=('iso')
bootmodes=('bios.syslinux' 'uefi.systemd-boot')
arch="x86_64"
pacman_conf="pacman.conf"
airootfs_image_type="squashfs"
file_permissions=(
  ["/etc/shadow"]="0:0:400"
)
"""

PACMAN_ARCH = """[options]
HoldPkg     = pacman glibc
Architecture = auto
SigLevel    = Required DatabaseOptional

[core]
Include = /etc/pacman.d/mirrorlist

[extra]
Include = /etc/pacman.d/mirrorlist
"""

PACMAN_CACHYOS = """[options]
Architecture = x86_64 x86_64_v3
SigLevel    = Required DatabaseOptional

[cachyos-v4]
Include = /etc/pacman.d/cachyos-v4-mirrorlist

[cachyos-core-v4]
Include = /etc/pacman.d/cachyos-v4-mirrorlist

[cachyos-znver4]
Include = /etc/pacman.d/cachyos-v4-mirrorlist

[cachyos-v3]
Include = /etc/pacman.d/cachyos-v3-mirrorlist

[cachyos-core-v3]
Include = /etc/pacman.d/cachyos-v3-mirrorlist

[cachyos-extra-v3]
Include = /etc/pacman.d/cachyos-v3-mirrorlist

[cachyos]
Include = /etc/pacman.d/cachyos-mirrorlist

[core]
Include = /etc/pacman.d/mirrorlist

[extra]
Include = /etc/pacman.d/mirrorlist
"""


def make_ebox(dest: Path) -> Path:
    """Minimal stand-in for a checkout of the ebox repo."""
    (dest / "bin").mkdir(parents=True, exist_ok=True)
    (dest / "systemd").mkdir(exist_ok=True)
    (dest / "bin" / "ebox").write_text("#!/usr/bin/env bash\necho ebox-stub\n")
    for unit in ["ebox-liveuser.service", "ebox-pull.service", "ebox-push.service", "ebox-push.timer"]:
        (dest / "systemd" / unit).write_text(f"[Unit]\nDescription={unit} (stub)\n")
    return dest


def make(kind: str, dest: Path) -> Path:
    if kind == "ebox":
        return make_ebox(dest)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "profiledef.sh").write_text(PROFILEDEF)
    if kind == "releng":
        (dest / "packages.x86_64").write_text("base\nlinux\nlinux-firmware\nmkinitcpio-archiso\n# comment\nzsh\n")
        (dest / "pacman.conf").write_text(PACMAN_ARCH)
    elif kind == "cachyos":
        (dest / "packages_desktop.x86_64").write_text("base\nlinux-cachyos\nlinux-firmware\ncachyos-settings\n")
        (dest / "pacman.conf").write_text(PACMAN_CACHYOS)
    else:
        raise ValueError(kind)
    units = dest / "airootfs" / "etc" / "systemd" / "system"
    for rel in [
        "multi-user.target.wants/iwd.service",
        "multi-user.target.wants/systemd-networkd.service",
        "network-online.target.wants/systemd-networkd-wait-online.service",
    ]:
        p = units / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.is_symlink():
            os.symlink(f"/usr/lib/systemd/system/{p.name}", p)
    (dest / "syslinux").mkdir(exist_ok=True)
    (dest / "syslinux" / "archiso_sys-linux.cfg").write_text(
        "LABEL arch64\nMENU LABEL Arch Linux install medium (x86_64, BIOS)\n"
    )
    entries = dest / "efiboot" / "loader" / "entries"
    entries.mkdir(parents=True, exist_ok=True)
    (entries / "01-archiso-x86_64-linux.conf").write_text("title    Arch Linux install medium (x86_64, UEFI)\n")
    return dest


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    print(make(sys.argv[1], Path(sys.argv[2])))
