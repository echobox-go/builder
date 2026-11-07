# Proxmox layout

| Guest | ID | Type | Size | Runs |
|---|---|---|---|---|
| `eb-build` | 210 | VM (Arch, UEFI) | 8 vCPU, 24 GB, 150 GB | forgejo-runner, archiso, CachyOS profile, pacoloco, echobox repo |
| `eb-portal` | 211 | LXC | 2 vCPU, 4 GB, 32 GB+ | `infra/portal/compose.yaml` |
| `eb-state` | 212 | LXC | 2 vCPU, 2 GB + data disk | `infra/state/compose.yaml` |
| `eb-edge` | 213 | LXC | 1 vCPU, 512 MB | `infra/edge/compose.yaml` |

`create-guests.sh` prints the `qm` / `pct` commands; `--apply` runs them on the
Proxmox host. Docker in unprivileged LXCs needs `nesting=1` (set by the script).

Network rules:
- `eb-build` → `eb-portal` (Git, ISO upload) and the internet (mirrors). **Not** `eb-state`.
- `eb-edge` → all published services, so Pangolin can reach them.
- Nothing else is exposed; Pangolin is the only way in.

After creating `eb-build`, install Arch from the ISO, then run
`infra/build/setup-build-vm.sh` on it.
