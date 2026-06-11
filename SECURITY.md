# Security & Privacy Model

Health OS is local-first by design. This document is the honest threat model — read it before running the software, and read [DISCLAIMER.md](DISCLAIMER.md) for the legal terms.

## Where your data lives

| Data | Location | Protection |
|---|---|---|
| Garmin email + password | `.env.local` (plaintext) | gitignored; filesystem permissions only |
| Garmin session token | `.garmin_session.pkl` | gitignored; filesystem permissions only |
| Health metrics (30-day sync) | `garmin_cache.json` | gitignored; local only |
| Food / nutrition log | `nutrition_log.json` | gitignored; local only |
| UI state, habits, manual entries | Browser localStorage | per-browser-profile |

Nothing is transmitted anywhere except: (a) requests to Garmin's API to fetch your own data, and (b) a CDN fallback for the Chart.js library if the local copy is missing.

## Hard rules

1. **Never expose the server.** It binds to `127.0.0.1:8787` and has no authentication, no TLS, and no rate limiting. Do not port-forward it, reverse-proxy it, run it on a VPS, or bind it to `0.0.0.0`. Anyone who can reach the port can read your health data and trigger syncs.
2. **Never commit `.env.local`, `*.pkl`, `garmin_cache.json`, or `nutrition_log.json`.** The provided `.gitignore` covers them — do not weaken it. If you ever committed credentials, rotate your Garmin password immediately and rewrite git history.
3. **Shared machines:** anyone with your OS user account can read your credentials and health data. Use full-disk encryption and a per-user account.
4. **Session pickle caution:** `.garmin_session.pkl` is a Python pickle. Never replace it with a pickle from an untrusted source — unpickling untrusted data executes arbitrary code. Delete it if in doubt; the server will just log in again.

## If you want remote access anyway

Don't expose this server. The acceptable patterns are: a VPN/private mesh (e.g. Tailscale) to your home machine, or a separate hardened deployment with authentication in front — both out of scope for this repo and at your own risk.

## Reporting

This is a hobby project with no security team and no SLA. Issues and PRs are welcome; treat the codebase as unaudited.
