# Health OS

A local-first personal health dashboard that turns your Garmin Connect data into a single operating view: healthspan age, 15 health-system scores, 30-day trends, an anatomical body focus map, nutrition tracking against RDAs, and evidence-cited recommendations.

**[Live demo](https://health-os-orcin.vercel.app/demo)** — fully synthetic data, nothing personal.

> ⚠️ **Read [DISCLAIMER.md](DISCLAIMER.md) before using.** This is not a medical device, the Garmin integration uses an unofficial API, and you run this software entirely at your own risk.

## What it does

- **Healthspan age model** — chronological age adjusted by nine evidence-anchored deltas (sleep duration/consistency, steps, WHO aerobic volume, vigorous minutes, strength time, VO₂max, resting HR, lean mass), each mapped from published hazard ratios via a Gompertz age-equivalence and capped to avoid runaway compounding. Full math in [METRIC_FORMULAS.md](METRIC_FORMULAS.md).
- **15 health-system scores** — cardiac, metabolic, muscle, cognitive, immune, inflammation, etc., each averaging its mapped 0–100 metric scores, optionally blended with 7-day nutrient coverage (15–35% weight by diet-sensitivity of the system).
- **Personal-baseline HRV scoring** — HRV is scored against your own Garmin balanced range, not population norms.
- **56 preset recommendations** — rule-based, each with a measurable trigger from your data, a concrete action, and a citation (WHO 2020, Paluch 2022, Momma 2022, Mandsager 2018, …).
- **Body focus map** — anatomical SVG (front muscles / organs / posterior chain) coloured by recent training stimulus, with per-tissue detail panels.
- **Nutrition** — log meals in plain English; nutrients (15 fields vs DRI/WHO/EFSA RDAs) feed the system scores. AI analysis requires your own AI integration (see below) or manual entry.
- **Local-first** — your data lives in `garmin_cache.json` and `nutrition_log.json` on your machine and in your browser's localStorage. Nothing is sent anywhere except to Garmin's API to fetch your own data.

## Architecture

```
┌─────────────────┐   unofficial API    ┌─────────────────┐
│  Garmin Connect │ ◄────────────────── │  server.py      │  Python 3.10+
└─────────────────┘  (garminconnect)    │  · auth + sync  │
                                        │  · 3h auto-sync │
                                        │  · JSON cache   │
                                        │  · static serve │
                                        └────────┬────────┘
                                                 │ http://127.0.0.1:8787
                                        ┌────────▼────────────────┐
                                        │ health-operating-       │
                                        │ system.html (the app)   │
                                        │ single file, no build   │
                                        └─────────────────────────┘
```

No database, no build step, no framework. One Python file, one HTML file.

## Quick start

```bash
git clone <this repo>
cd healthos
pip install garminconnect

cp .env.example .env.local
# edit .env.local with your Garmin email + password

python server.py
# open http://127.0.0.1:8787
```

First sync takes ~60–90 s (30 nights of sleep data are fetched sequentially). After that the cache loads instantly and a background thread re-syncs every 3 hours (`SYNC_INTERVAL_MIN` to change).

## Security & privacy model (read this)

- Your Garmin credentials sit in **plaintext** in `.env.local` and a session token is pickled to `.garmin_session.pkl`. Both are gitignored. Protect the machine they live on.
- The server binds to `127.0.0.1` only. **Do not** port-forward or expose it — it has no authentication.
- All health data stays on your machine. There is no telemetry, no analytics, no external calls except Garmin's API (and a CDN fallback for Chart.js).
- More detail in [SECURITY.md](SECURITY.md).

## AI integration (optional, bring your own)

Food-log nutrient analysis and the AI coach expect an AI backend. Out of the box they degrade gracefully (food entries are saved as "pending"). Options: add an Anthropic key and the `/api/ai/*` endpoints (commented scaffold in `server.py`), or analyse pending entries with any LLM and POST results to `/api/food` (schema in the code).

## Documentation

- [METRIC_FORMULAS.md](METRIC_FORMULAS.md) — every formula, its evidence base, and an honest limitations list
- [SECURITY.md](SECURITY.md) — threat model and safeguards
- [DISCLAIMER.md](DISCLAIMER.md) — legal disclaimer and conditions of use

## License

MIT — see [LICENSE](LICENSE). Use of the software constitutes acceptance of the [DISCLAIMER](DISCLAIMER.md).
