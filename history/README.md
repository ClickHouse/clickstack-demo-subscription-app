# Demo-app history

Weeks of telemetry from this app, with incidents planted, for labs that need more than what a learner generates live — a 28-day error budget, for one. It is made from recordings of the real app, so the schema and attributes are exactly what its SDKs send.

## Load it

Run it again before each delivery: timestamps are relative to the moment you run it.

```bash
python3 history/history.py generate --send
```

It reads `OTEL_EXPORTER_OTLP_ENDPOINT` and `OTEL_EXPORTER_OTLP_HEADERS` from the shell, or from the app's `.env` when they aren't set there.

Check the plan without sending anything with `--dry-run`, or write OTLP JSON files with `--out DIR`. At the default `--scale 0.2`, which matches the single Locust user in `docker-compose.managed.yml`, it loads about 1.7 million spans and 1.5 million logs, roughly 3 GB of uncompressed JSON. That took about 3 minutes in testing; if the endpoint throttles, the script retries and reports how often.

What it plants, relative to now:

| Incident | Default | What it looks like |
| --- | --- | --- |
| Docs-crash burn | 9 days ago, 10:20 UTC, 40 minutes | `GET /load-docs` fails and `docs-loader` restarts; exactly 40% of the error budget |
| Bad deploy | 2.0.0, 2 days ago, 13:05 UTC, 5 hours, then back to 1.0.0 | Signups slow down, a share of them time out, and a new warning appears; exactly 30% of the error budget |

The budget is for a 99.9% SLO over user requests: every `subscription-backend` server span except `GET /health`. User traffic follows a daily cycle and halves at weekends; health checks don't. Every option is in `history.py generate --help`.

## Re-record it

Only needed when the app's telemetry changes. Requires Docker.

```bash
history/capture.sh v1        # 1.0.0 traffic, then a Docs burn
history/capture.sh v2        # 2.0.0, the bad deploy
python3 history/history.py templates
```

The recordings go to `capture/` (not committed); `templates.json.gz` is what the generator reads.
