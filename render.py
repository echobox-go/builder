#!/usr/bin/env python3
"""Render an echobox-go profile.yaml into an archiso profile directory.

    render.py validate profiles/users/*/profile.yaml
    render.py render profiles/users/niklas/profile.yaml \
        --base-dir /usr/share/archiso/configs/releng --out build/niklas/profile

The output is a normal archiso profile that `mkarchiso` can build. It contains
public configuration only: no passwords, keys or tokens.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import sys
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import jsonschema
import yaml

REPO_ROOT = Path(__file__).resolve().parent
SCHEMA_PATH = REPO_ROOT / "profiles" / "schema" / "profile.schema.json"
KEYMAPS_PATH = REPO_ROOT / "keymaps.yaml"
DESKTOPS_PATH = REPO_ROOT / "desktops.yaml"
# Checkout of github.com/echobox-go/ebox; by default the sibling folder ../ebox.
EBOX_DIR = Path(os.environ.get("EBOX_DIR", REPO_ROOT.parent / "ebox"))
BRAND_DIR = REPO_ROOT / "brand"

# Runtime dependencies of `ebox` that are in the official repositories.
AGENT_PACKAGES = ["bash", "curl", "jq", "git", "restic", "chezmoi", "bitwarden-cli", "cryptsetup", "sudo"]
# Runtime dependencies that only exist in the AUR (prebuilt into the echobox repo).
AGENT_AUR = ["aconfmgr-git"]

# Units shipped in the ebox repo (systemd/) and enabled in the live image.
ENABLED_UNITS = {
    "multi-user.target.wants": ["ebox-liveuser.service", "ebox-pull.service"],
}
# Network units in the releng profile that conflict with NetworkManager.
RELENG_NETWORK_UNITS = [
    "multi-user.target.wants/iwd.service",
    "multi-user.target.wants/systemd-networkd.service",
    "network-online.target.wants/systemd-networkd-wait-online.service",
    "sockets.target.wants/systemd-networkd.socket",
]
BOOT_TITLE_RE = re.compile(r"Arch Linux install medium")
PROFILE_DEFAULTS = {
    "cpu_level": "generic",
    "locale": "C.UTF-8",
    "timezone": "UTC",
    "shell": "bash",
    "packages": [],
    "aur": [],
    "persistence": "luks-passphrase",
}
SYNC_DEFAULTS = {"home_paths": [], "dotfiles": True, "desktop_settings": True, "packages": True}


class RenderError(Exception):
    """The profile cannot be rendered as requested."""


@dataclass
class RenderResult:
    user: str
    out_dir: Path
    iso_name: str
    packages_added: list[str] = field(default_factory=list)
    aur_added: list[str] = field(default_factory=list)
    repos_removed: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        d = self.__dict__.copy()
        d["out_dir"] = str(self.out_dir)
        return d


# --------------------------------------------------------------------------- loading


def _load_yaml(path: Path):
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_profile(path: Path) -> dict:
    """Load, validate and fill in defaults for a profile."""
    data = _load_yaml(path)
    if not isinstance(data, dict):
        raise RenderError(f"{path}: profile must be a mapping")
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    try:
        jsonschema.validate(data, schema)
    except jsonschema.ValidationError as exc:
        where = "/".join(str(p) for p in exc.absolute_path) or "(root)"
        raise RenderError(f"{path}: {where}: {exc.message}") from None
    profile = {**PROFILE_DEFAULTS, **data}
    profile["sync"] = {**SYNC_DEFAULTS, **data.get("sync", {})}
    profile.setdefault("hostname", f"echobox-{profile['user']}".replace("_", "-"))
    return profile


def resolve_keymap(keymap, keymaps: dict) -> dict:
    if isinstance(keymap, dict):
        return {"xkb_variant": "", **keymap}
    if keymap not in keymaps:
        known = ", ".join(sorted(keymaps))
        raise RenderError(f"unknown keymap {keymap!r}; known: {known}")
    return {"xkb_variant": "", **keymaps[keymap]}


# --------------------------------------------------------------------------- helpers


def find_packages_file(base: Path) -> Path:
    plain = base / "packages.x86_64"
    if plain.is_file():
        return plain
    candidates = sorted(base.glob("packages*.x86_64"))
    if len(candidates) == 1:
        return candidates[0]
    raise RenderError(f"{base}: expected one packages*.x86_64 file, found {len(candidates)}")


def read_package_list(path: Path) -> list[str]:
    pkgs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            pkgs.append(line)
    return pkgs


def append_packages(path: Path, extra: list[str], header: str) -> list[str]:
    existing = set(read_package_list(path))
    added = []
    for pkg in extra:
        if pkg not in existing and pkg not in added:
            added.append(pkg)
    if added:
        text = path.read_text(encoding="utf-8")
        if text and not text.endswith("\n"):
            text += "\n"
        text += f"\n# --- {header} ---\n" + "\n".join(added) + "\n"
        path.write_text(text, encoding="utf-8")
    return added


def _split_pacman_sections(text: str) -> list[tuple[str | None, list[str]]]:
    sections: list[tuple[str | None, list[str]]] = [(None, [])]
    for line in text.splitlines():
        m = re.match(r"^\s*\[([^\]]+)\]\s*$", line)
        if m:
            sections.append((m.group(1), [line]))
        else:
            sections[-1][1].append(line)
    return sections


def filter_pacman_conf(text: str, base: str, cpu_level: str, repo_url: str | None) -> tuple[str, list[str]]:
    """Drop CachyOS repos above the chosen CPU level and add the echobox repo."""
    if base == "cachyos":
        drop = {"generic": r"-(v3|v4|znver4)$", "v3": r"-(v4|znver4)$", "v4": r"-znver4$"}[cpu_level]
    else:
        drop = None
    removed = []
    out: list[str] = []
    inserted = False
    for name, lines in _split_pacman_sections(text):
        if name and drop and re.search(drop, name):
            removed.append(name)
            continue
        if name and name != "options" and repo_url and not inserted:
            # Listed first so prebuilt AUR packages win over nothing else.
            out += [
                "[echobox]",
                "# Own repo with AUR builds (aurutils on eb-build). Sign packages and",
                "# lsign the key on the build VM; see infra/build/README.md.",
                "SigLevel = Required DatabaseOptional",
                f"Server = {repo_url}",
                "",
            ]
            inserted = True
        out += lines
    if repo_url and not inserted:
        out += ["", "[echobox]", "SigLevel = Required DatabaseOptional", f"Server = {repo_url}"]
    return "\n".join(out) + "\n", removed


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def symlink(path: Path, target: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or path.exists():
        path.unlink()
    os.symlink(target, path)


def shell_assign(name: str, value) -> str:
    if isinstance(value, bool):
        value = "1" if value else "0"
    elif isinstance(value, (list, tuple)):
        value = " ".join(value)
    return f"{name}={shlex.quote(str(value))}"


# --------------------------------------------------------------------------- render


def render(
    profile: dict,
    base_dir: Path,
    out_dir: Path,
    portal_url: str,
    repo_url: str | None = None,
    force: bool = False,
    ebox_dir: Path | None = None,
) -> RenderResult:
    keymaps = _load_yaml(KEYMAPS_PATH)
    desktops = _load_yaml(DESKTOPS_PATH)
    ebox_dir = Path(ebox_dir or EBOX_DIR)
    if not (ebox_dir / "bin" / "ebox").is_file():
        raise RenderError(f"{ebox_dir}: no bin/ebox; clone github.com/echobox-go/ebox next to builder or set EBOX_DIR")
    user = profile["user"]
    desktop_name = profile["desktop"]
    desktop = desktops.get(desktop_name, {}) if desktop_name != "none" else {}
    keymap = resolve_keymap(profile["keymap"], keymaps)

    if not (base_dir / "profiledef.sh").is_file():
        raise RenderError(f"{base_dir}: not an archiso profile (no profiledef.sh)")
    if out_dir.exists():
        if not force:
            raise RenderError(f"{out_dir} exists; pass --force to replace it")
        shutil.rmtree(out_dir)
    shutil.copytree(base_dir, out_dir, symlinks=True)

    result = RenderResult(user=user, out_dir=out_dir, iso_name=f"echobox-go-{user}")
    air = out_dir / "airootfs"
    etc = air / "etc"
    units = etc / "systemd" / "system"

    # Packages ---------------------------------------------------------------
    pkgs = list(AGENT_PACKAGES)
    pkgs.append(profile["shell"])
    if profile["locale"] != "C.UTF-8":
        pkgs.append("glibc-locales")  # precompiled locales; no locale-gen at boot
    if desktop:
        pkgs += desktops["common"]["packages"] + desktop["packages"]
    pkgs += profile["packages"]

    aur = list(profile["aur"])
    agent_aur = AGENT_AUR + desktop.get("agent_aur", [])
    if repo_url:
        aur += agent_aur
    else:
        if aur:
            raise RenderError(f"profile lists AUR packages {aur} but no --repo-url was given")
        result.warnings.append(
            f"no echobox repo configured; skipping AUR helpers {agent_aur} (ebox degrades without them)"
        )

    pkg_file = find_packages_file(out_dir)
    result.packages_added = append_packages(pkg_file, pkgs, f"echobox-go: {user}")
    if aur:
        result.aur_added = append_packages(pkg_file, aur, "echobox-go: AUR (echobox repo)")

    pacman_conf = out_dir / "pacman.conf"
    if pacman_conf.is_file():
        text, result.repos_removed = filter_pacman_conf(
            pacman_conf.read_text(encoding="utf-8"), profile["base"], profile["cpu_level"], repo_url
        )
        pacman_conf.write_text(text, encoding="utf-8")
    elif profile["base"] == "cachyos" or repo_url:
        raise RenderError(f"{base_dir}: no pacman.conf to adjust")

    # System identity --------------------------------------------------------
    write(etc / "hostname", profile["hostname"] + "\n")
    write(etc / "locale.conf", f"LANG={profile['locale']}\n")
    write(etc / "vconsole.conf", f"KEYMAP={keymap['console']}\n")
    xkb = [
        'Section "InputClass"',
        '        Identifier "system-keyboard"',
        '        MatchIsKeyboard "on"',
        f'        Option "XkbLayout" "{keymap["xkb_layout"]}"',
    ]
    if keymap["xkb_variant"]:
        xkb.append(f'        Option "XkbVariant" "{keymap["xkb_variant"]}"')
    xkb.append("EndSection")
    write(etc / "X11" / "xorg.conf.d" / "00-keyboard.conf", "\n".join(xkb) + "\n")
    symlink(etc / "localtime", f"/usr/share/zoneinfo/{profile['timezone']}")

    # Desktop ----------------------------------------------------------------
    if desktop:
        symlink(units / "display-manager.service", f"/usr/lib/systemd/system/{desktop['display_manager']}")
        symlink(units / "default.target", "/usr/lib/systemd/system/graphical.target")
        for rel in RELENG_NETWORK_UNITS:
            p = units / rel
            if p.is_symlink() or p.exists():
                p.unlink()
        symlink(units / "multi-user.target.wants" / "NetworkManager.service",
                "/usr/lib/systemd/system/NetworkManager.service")
        symlink(units / "network-online.target.wants" / "NetworkManager-wait-online.service",
                "/usr/lib/systemd/system/NetworkManager-wait-online.service")
        session = desktop["session"]
        if desktop["autologin"] == "sddm":
            write(etc / "sddm.conf.d" / "50-echobox-autologin.conf",
                  f"[Autologin]\nUser={user}\nSession={session}\n")
        elif desktop["autologin"] == "gdm":
            write(etc / "gdm" / "custom.conf",
                  f"[daemon]\nAutomaticLoginEnable=True\nAutomaticLogin={user}\n")
        elif desktop["autologin"] == "lightdm":
            write(etc / "lightdm" / "lightdm.conf.d" / "50-echobox-autologin.conf",
                  f"[Seat:*]\nautologin-user={user}\nautologin-session={session}\n")

    # ebox ---------------------------------------------------------------------
    ebox_bin = air / "usr" / "local" / "bin" / "ebox"
    ebox_bin.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ebox_dir / "bin" / "ebox", ebox_bin)
    for unit in sorted((ebox_dir / "systemd").glob("ebox-*")):
        units.mkdir(parents=True, exist_ok=True)
        shutil.copy2(unit, units / unit.name)
    for wants, names in ENABLED_UNITS.items():
        for name in names:
            symlink(units / wants / name, f"/etc/systemd/system/{name}")

    sync = profile["sync"]
    conf = [
        "# Generated by echobox-go builder (render.py) from profile.yaml. Public values only.",
        shell_assign("EBOX_USER", user),
        shell_assign("EBOX_DISPLAY_NAME", profile.get("display_name", user)),
        shell_assign("EBOX_SHELL", f"/usr/bin/{profile['shell']}"),
        shell_assign("EBOX_GROUPS", ["wheel"] + desktop.get("groups", [])),
        shell_assign("EBOX_BASE", profile["base"]),
        shell_assign("EBOX_DESKTOP", desktop_name),
        shell_assign("EBOX_SETTINGS_TOOL", desktop.get("settings_tool", "none")),
        shell_assign("EBOX_PORTAL_URL", portal_url),
        shell_assign("EBOX_PERSISTENCE", profile["persistence"]),
        shell_assign("EBOX_HOME_PATHS", sync["home_paths"]),
        shell_assign("EBOX_SYNC_DOTFILES", sync["dotfiles"]),
        shell_assign("EBOX_SYNC_DESKTOP", sync["desktop_settings"]),
        shell_assign("EBOX_SYNC_PACKAGES", sync["packages"]),
    ]
    write(etc / "ebox" / "ebox.conf", "\n".join(conf) + "\n")

    # Branding -----------------------------------------------------------------
    pixmaps = air / "usr" / "share" / "pixmaps"
    pixmaps.mkdir(parents=True, exist_ok=True)
    shutil.copy2(BRAND_DIR / "mark-dark.svg", pixmaps / "echobox-go.svg")
    write(etc / "motd", (
        "\n  echobox-go  ·  Your Linux environment, on any computer.\n\n"
        "  First boot: connect to the network (nmtui), then run `ebox enrol`.\n"
        "  Later: `ebox pull` to fetch your latest environment, `ebox push` to save it.\n\n"
        "  echobox-go is an independent project and is not affiliated with Arch Linux or CachyOS.\n\n"
    ))
    title = f"echobox-go live ({user})"
    for sub in ("syslinux", "grub", "efiboot"):
        for cfg in (out_dir / sub).rglob("*") if (out_dir / sub).is_dir() else []:
            if cfg.is_file() and cfg.suffix in {".cfg", ".conf"}:
                text = cfg.read_text(encoding="utf-8", errors="surrogateescape")
                new = BOOT_TITLE_RE.sub(title, text)
                if new != text:
                    cfg.write_text(new, encoding="utf-8", errors="surrogateescape")

    # profiledef.sh --------------------------------------------------------------
    profiledef = out_dir / "profiledef.sh"
    block = [
        "",
        "# --- echobox-go builder (render.py) ---",
        shell_assign("iso_name", result.iso_name),
        'iso_label="EBGO_$(date --date="@${SOURCE_DATE_EPOCH:-$(date +%s)}" +%Y%m)"',
        shell_assign("iso_publisher", "echobox-go <https://github.com/echobox-go>"),
        shell_assign("iso_application", title),
        'file_permissions+=(["/usr/local/bin/ebox"]="0:0:755")',
        'file_permissions+=(["/etc/ebox/ebox.conf"]="0:0:644")',
    ]
    with profiledef.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(block) + "\n")

    for w in result.warnings:
        warnings.warn(w, stacklevel=2)
    return result


# --------------------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("validate", help="validate one or more profile.yaml files")
    v.add_argument("profiles", nargs="+", type=Path)

    r = sub.add_parser("render", help="render a profile into an archiso profile directory")
    r.add_argument("profile", type=Path)
    r.add_argument("--base-dir", type=Path, required=True,
                   help="base archiso profile (releng, or the pinned CachyOS profile)")
    r.add_argument("--out", type=Path, required=True)
    r.add_argument("--portal-url", default=os.environ.get("EBOX_PORTAL_URL", "https://portal.example.invalid"))
    r.add_argument("--repo-url", default=os.environ.get("EBOX_REPO_URL") or None,
                   help="pacman Server URL of the echobox repo with AUR builds")
    r.add_argument("--force", action="store_true", help="replace --out if it exists")
    r.add_argument("--ebox-dir", type=Path, default=None,
                   help="checkout of the ebox repo (default: $EBOX_DIR or ../ebox)")
    r.add_argument("--json", action="store_true", help="print a JSON summary")

    args = ap.parse_args(argv)
    try:
        if args.cmd == "validate":
            keymaps = _load_yaml(KEYMAPS_PATH)
            for p in args.profiles:
                prof = load_profile(p)
                resolve_keymap(prof["keymap"], keymaps)
                print(f"ok  {p}")
            return 0
        prof = load_profile(args.profile)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            res = render(prof, args.base_dir, args.out, args.portal_url, args.repo_url, args.force, args.ebox_dir)
        for w in res.warnings:
            print(f"warning: {w}", file=sys.stderr)
        if args.json:
            print(json.dumps(res.as_dict(), indent=2))
        else:
            print(f"rendered {res.user} -> {res.out_dir} ({len(res.packages_added)} packages added)")
        return 0
    except RenderError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
