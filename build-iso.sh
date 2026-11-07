#!/usr/bin/env bash
# Build one user's echobox-go live ISO on the eb-build VM.
#
#   ./build-iso.sh --user niklas [--out DIR] [--work DIR] [--base-dir DIR]
#
# Rendering runs as the calling user; only mkarchiso runs as root (via sudo when
# not already root; infra/build/setup-build-vm.sh allows exactly that).
# Needs the ebox repo next to this one (../ebox) or EBOX_DIR set.
#
# Base profile by `base:` in profile.yaml:
#   arch     /usr/share/archiso/configs/releng            (package: archiso)
#   cachyos  $CACHYOS_PROFILE_DIR                         (pinned CachyOS-Live-ISO checkout;
#                                                          path confirmed in roadmap phase 0)
# Environment: EBOX_PORTAL_URL, EBOX_REPO_URL (optional, enables AUR packages).

set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
user="" out="" work="" base_dir=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --user) user="$2"; shift 2 ;;
        --out) out="$2"; shift 2 ;;
        --work) work="$2"; shift 2 ;;
        --base-dir) base_dir="$2"; shift 2 ;;
        -h|--help) sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown option $1" >&2; exit 2 ;;
    esac
done

[[ -n "$user" ]] || { echo "--user is required" >&2; exit 2; }
if [[ $EUID -eq 0 ]]; then mkarchiso=(mkarchiso); else mkarchiso=(sudo -n mkarchiso); fi
command -v mkarchiso >/dev/null || { echo "mkarchiso not found: pacman -S archiso" >&2; exit 1; }

profile="$root/profiles/users/$user/profile.yaml"
[[ -f "$profile" ]] || { echo "no profile at $profile" >&2; exit 1; }

if [[ -z "$base_dir" ]]; then
    base="$(python3 -c 'import sys,yaml; print(yaml.safe_load(open(sys.argv[1]))["base"])' "$profile")"
    case "$base" in
        arch) base_dir=/usr/share/archiso/configs/releng ;;
        cachyos) base_dir="${CACHYOS_PROFILE_DIR:?set CACHYOS_PROFILE_DIR to the pinned CachyOS archiso profile}" ;;
        *) echo "unknown base $base" >&2; exit 1 ;;
    esac
fi

build="$root/build/$user"
out="${out:-$build/out}"
work="${work:-$build/work}"
rendered="$build/profile"

python3 "$root/render.py" render "$profile" \
    --base-dir "$base_dir" --out "$rendered" --force

[[ -e "$work" ]] && { echo "$work exists (failed earlier build?); remove it as root first" >&2; exit 1; }
mkdir -p "$out"
SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-$(git -C "$root" log -1 --format=%ct 2>/dev/null || date +%s)}"
export SOURCE_DATE_EPOCH
# -r removes the (root-owned) work directory when done.
"${mkarchiso[@]}" -v -r -w "$work" -o "$out" "$rendered"

iso="$(find "$out" -maxdepth 1 -name "echobox-go-$user-*.iso" -printf '%T@ %p\n' | sort -n | tail -n1 | cut -d' ' -f2-)"
[[ -n "$iso" ]] || { echo "build finished but no ISO found in $out" >&2; exit 1; }
(cd "$(dirname "$iso")" && sha256sum "$(basename "$iso")" > "$(basename "$iso").sha256")
echo "$iso"
