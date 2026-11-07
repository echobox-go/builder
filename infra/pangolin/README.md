# Pangolin resources

Site: one Newt connector on `eb-edge` (`infra/edge/compose.yaml`).

## Public resources (browser, Pangolin SSO)

| Resource | Target | Notes |
|---|---|---|
| `portal.<domain>` | `eb-portal:8080` | Add custom header `X-Ebox-Proxy-Token` = `EBOX_PROXY_TOKEN` |
| `git.<domain>` | `eb-portal:3000` | Forgejo |
| `iso.<domain>` | `eb-portal:8082` | ISO downloads; same SSO so phones can download after login |

Use SSO (or email OTP tied to a user) so Pangolin forwards `Remote-User`. PIN,
password and share-link auth carry no identity and won't work with the portal.

## Private resources (machine clients only)

| Resource | Target | Who |
|---|---|---|
| restic | `eb-state:8000` | enrolled sticks and machines |
| vault | `eb-state:8081` | enrolled sticks and machines |
| agent API | `eb-portal:8080` path `/api/agent/*` | enrolled sticks and machines |
| pacoloco | `eb-build:9129` | optional, for `ebox pull` package installs |

One machine client per stick, granted directly on these resources (role
assignment for machine clients depends on the Pangolin edition). Deleting the
client tears down that stick's tunnel.
