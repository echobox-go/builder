from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import render  # noqa: E402
from fixtures import make, make_ebox  # noqa: E402

REPO = HERE.parent
PROFILES = sorted((REPO / "profiles" / "users").glob("*/profile.yaml"))


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def packages(out: Path) -> list[str]:
    return render.read_package_list(render.find_packages_file(out))


@pytest.fixture(autouse=True)
def ebox_stub(tmp_path, monkeypatch):
    """Tests run without the ebox repo: point the renderer at a stub."""
    d = make_ebox(tmp_path / "ebox")
    monkeypatch.setattr(render, "EBOX_DIR", d)
    return d


@pytest.fixture
def releng(tmp_path):
    return make("releng", tmp_path / "releng")


@pytest.fixture
def cachyos(tmp_path):
    return make("cachyos", tmp_path / "cachyos")


def do_render(profile_path, base, tmp_path, **kw):
    prof = render.load_profile(profile_path)
    out = tmp_path / "out"
    with pytest.warns(UserWarning) if not kw.get("repo_url") else _nullctx():
        res = render.render(prof, base, out, "https://portal.test", **kw)
    return prof, res, out


class _nullctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.mark.parametrize("path", PROFILES, ids=lambda p: p.parent.name)
def test_example_profiles_validate(path):
    prof = render.load_profile(path)
    assert prof["user"] == path.parent.name


def test_emil_arch_dvorak_gnome(releng, tmp_path):
    _, res, out = do_render(REPO / "profiles/users/emil/profile.yaml", releng, tmp_path)
    etc = out / "airootfs" / "etc"
    assert read(etc / "vconsole.conf") == "KEYMAP=dvorak\n"
    kb = read(etc / "X11/xorg.conf.d/00-keyboard.conf")
    assert '"XkbLayout" "us"' in kb and '"XkbVariant" "dvorak"' in kb
    assert read(etc / "locale.conf") == "LANG=en_US.UTF-8\n"
    assert os.readlink(etc / "localtime") == "/usr/share/zoneinfo/Europe/Stockholm"
    assert read(etc / "hostname") == "echobox-emil\n"
    units = etc / "systemd/system"
    assert os.readlink(units / "display-manager.service") == "/usr/lib/systemd/system/gdm.service"
    assert os.readlink(units / "default.target").endswith("graphical.target")
    assert not (units / "multi-user.target.wants/iwd.service").is_symlink()
    assert (units / "multi-user.target.wants/NetworkManager.service").is_symlink()
    assert "AutomaticLogin=emil" in read(etc / "gdm/custom.conf")
    pk = packages(out)
    for p in ["gnome", "gdm", "networkmanager", "glibc-locales", "firefox", "vim", "restic", "chezmoi"]:
        assert p in pk
    assert len(pk) == len(set(pk)), "packages must not be duplicated"
    # releng's pacman.conf untouched for arch without a repo
    assert read(out / "pacman.conf") == read(releng / "pacman.conf")
    assert res.repos_removed == []


def test_niklas_cachyos_generic_strips_cpu_repos(cachyos, tmp_path):
    _, res, out = do_render(REPO / "profiles/users/niklas/profile.yaml", cachyos, tmp_path)
    conf = read(out / "pacman.conf")
    for name in ["cachyos-v3", "cachyos-core-v3", "cachyos-extra-v3", "cachyos-v4", "cachyos-core-v4", "cachyos-znver4"]:
        assert f"[{name}]" not in conf
    assert "[cachyos]" in conf and "[core]" in conf and "[extra]" in conf
    assert set(res.repos_removed) == {"cachyos-v4", "cachyos-core-v4", "cachyos-znver4",
                                      "cachyos-v3", "cachyos-core-v3", "cachyos-extra-v3"}
    # packages went into the CachyOS-style list file
    assert "plasma-meta" in read(out / "packages_desktop.x86_64")
    assert "User=niklas" in read(out / "airootfs/etc/sddm.conf.d/50-echobox-autologin.conf")
    assert read(out / "airootfs/etc/vconsole.conf") == "KEYMAP=sv-latin1\n"


def test_cpu_level_v3_keeps_v3(cachyos, tmp_path):
    prof = render.load_profile(REPO / "profiles/users/niklas/profile.yaml")
    prof["cpu_level"] = "v3"
    with pytest.warns(UserWarning):
        res = render.render(prof, cachyos, tmp_path / "out", "https://portal.test")
    conf = read(tmp_path / "out/pacman.conf")
    assert "[cachyos-v3]" in conf and "[cachyos-v4]" not in conf
    assert "cachyos-v3" not in res.repos_removed


def test_ebox_installed_and_enabled(releng, tmp_path, ebox_stub):
    _, _, out = do_render(REPO / "profiles/users/emil/profile.yaml", releng, tmp_path)
    air = out / "airootfs"
    assert (air / "usr/local/bin/ebox").read_bytes() == (ebox_stub / "bin/ebox").read_bytes()
    wants = air / "etc/systemd/system/multi-user.target.wants"
    assert os.readlink(wants / "ebox-pull.service") == "/etc/systemd/system/ebox-pull.service"
    assert (air / "etc/systemd/system/ebox-pull.service").is_file()
    conf = read(air / "etc/ebox/ebox.conf")
    assert "EBOX_USER=emil" in conf
    assert "EBOX_PORTAL_URL=https://portal.test" in conf
    assert "EBOX_SETTINGS_TOOL=dconf" in conf
    assert "EBOX_HOME_PATHS='Documents .ssh'" in conf
    # the generated config must be valid shell and carry no secrets
    r = subprocess.run(["bash", "-n", str(air / "etc/ebox/ebox.conf")], capture_output=True)
    assert r.returncode == 0, r.stderr
    assert "PASSWORD" not in conf and "TOKEN" not in conf and "SECRET" not in conf


def test_branding_and_profiledef(releng, tmp_path):
    _, res, out = do_render(REPO / "profiles/users/emil/profile.yaml", releng, tmp_path)
    pdef = read(out / "profiledef.sh")
    assert "iso_name=echobox-go-emil" in pdef
    assert '["/usr/local/bin/ebox"]="0:0:755"' in pdef
    r = subprocess.run(["bash", "-n", str(out / "profiledef.sh")], capture_output=True)
    assert r.returncode == 0, r.stderr
    # Last assignment wins when mkarchiso sources the file.
    r = subprocess.run(["bash", "-c", f'declare -A file_permissions=(); source "{out}/profiledef.sh"; echo "$iso_name|$iso_label|${{file_permissions[/usr/local/bin/ebox]}}"'],
                       capture_output=True, text=True, check=True)
    name, label, perm = r.stdout.strip().split("|")
    assert name == "echobox-go-emil" and label.startswith("EBGO_") and perm == "0:0:755"
    assert "Arch Linux install medium" not in read(out / "syslinux/archiso_sys-linux.cfg")
    assert "echobox-go live (emil)" in read(out / "efiboot/loader/entries/01-archiso-x86_64-linux.conf")
    assert (out / "airootfs/usr/share/pixmaps/echobox-go.svg").is_file()
    assert "not affiliated with Arch Linux or CachyOS" in read(out / "airootfs/etc/motd")


def test_repo_url_adds_echobox_repo_and_aur(releng, tmp_path):
    prof = render.load_profile(REPO / "profiles/users/emil/profile.yaml")
    prof["aur"] = ["yay-bin"]
    res = render.render(prof, releng, tmp_path / "out", "https://portal.test",
                        repo_url="https://repo.example/$arch")
    conf = read(tmp_path / "out/pacman.conf")
    assert conf.index("[echobox]") < conf.index("[core]")
    assert "Server = https://repo.example/$arch" in conf
    assert "yay-bin" in res.aur_added and "aconfmgr-git" in res.aur_added


def test_aur_without_repo_fails(releng, tmp_path):
    prof = render.load_profile(REPO / "profiles/users/emil/profile.yaml")
    prof["aur"] = ["yay-bin"]
    with pytest.raises(render.RenderError, match="AUR"):
        render.render(prof, releng, tmp_path / "out", "https://portal.test")


def test_refuses_existing_out_without_force(releng, tmp_path):
    prof = render.load_profile(REPO / "profiles/users/emil/profile.yaml")
    (tmp_path / "out").mkdir()
    with pytest.raises(render.RenderError, match="exists"):
        render.render(prof, releng, tmp_path / "out", "https://portal.test")


@pytest.mark.parametrize("bad, msg", [
    ({"user": "Bad Name", "base": "arch", "desktop": "none", "keymap": "us"}, "user"),
    ({"user": "x", "base": "debian", "desktop": "none", "keymap": "us"}, "base"),
    ({"user": "x", "base": "arch", "desktop": "none", "keymap": "us", "password": "hunter2"}, "password"),
])
def test_schema_rejects(tmp_path, bad, msg):
    import yaml
    p = tmp_path / "profile.yaml"
    p.write_text(yaml.safe_dump(bad))
    with pytest.raises(render.RenderError, match=msg):
        render.load_profile(p)


def test_unknown_keymap(tmp_path):
    with pytest.raises(render.RenderError, match="unknown keymap"):
        render.resolve_keymap("klingon", render._load_yaml(render.KEYMAPS_PATH))


def test_keymaps_table_parses_no_as_string():
    km = render._load_yaml(render.KEYMAPS_PATH)
    assert "no" in km and km["no"]["xkb_layout"] == "no"


def test_cli_validate():
    r = subprocess.run([sys.executable, str(REPO / "render.py"), "validate", *map(str, PROFILES)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout.count("ok ") == len(PROFILES)


def test_missing_ebox_repo_is_a_clear_error(releng, tmp_path):
    prof = render.load_profile(REPO / "profiles/users/emil/profile.yaml")
    with pytest.raises(render.RenderError, match="echobox-go/ebox"):
        render.render(prof, releng, tmp_path / "out", "https://portal.test", ebox_dir=tmp_path / "nope")
