#!/usr/bin/env bash
# Record the app's telemetry for the history generator, one phase per version.
#   history/capture.sh v1   # 1.0.0: normal traffic, then a Docs burn
#   history/capture.sh v2   # 2.0.0: the bad deploy
# Output: history/capture/<phase>/{traces,logs}.jsonl (OTLP JSON, one batch per line)
set -euo pipefail
cd "$(dirname "$0")/.."
phase=${1:?usage: capture.sh v1|v2}
normal_seconds=${NORMAL_SECONDS:-240}
burn_seconds=${BURN_SECONDS:-120}

# Not used while recording, but the compose file requires them. Compose reads
# them for its own telemetry too, so the header has to look like one.
export OTEL_EXPORTER_OTLP_ENDPOINT=http://unused OTEL_EXPORTER_OTLP_HEADERS=unused=unused
compose() { docker compose -f docker-compose.managed.yml -f history/docker-compose.capture.yml "$@"; }

# Record with 5 Locust users, whatever the compose default: more traffic gives
# more templates, and history.py's --scale is relative to this rate.
export LOCUST_USERS=5

case $phase in
  v1) export APP_VERSION=1.0.0 FAULT_LATENCY_MS=0 FAULT_ERROR_RATE=0 ;;
  v2) export APP_VERSION=2.0.0 FAULT_LATENCY_MS=${FAULT_LATENCY_MS:-1500} FAULT_ERROR_RATE=${FAULT_ERROR_RATE:-0.2} ;;
  *) echo "unknown phase $phase" >&2; exit 1 ;;
esac

# A fresh folder per recording: Docker Desktop can keep stale entries for files
# deleted on the host, and the file exporter then fails to open them.
export CAPTURE_DIR="$PWD/history/capture/.recording-$(date +%s)"
mkdir -p "$CAPTURE_DIR"
compose up -d --force-recreate
sleep 10
if [ "$(docker inspect -f '{{.State.Running}}' otel-collector)" != true ]; then
  echo "the agent failed to start:" >&2
  docker logs otel-collector 2>&1 | tail -3 >&2
  exit 1
fi
echo "recording $phase normal traffic for ${normal_seconds}s"
sleep "$normal_seconds"
if [ "$phase" = v1 ]; then
  echo "recording a Docs burn for ${burn_seconds}s"
  compose up -d docs-burn
  sleep "$burn_seconds"
  compose stop docs-burn
fi
sleep 20   # let the batch processor flush
compose stop otel-collector
rm -rf "history/capture/$phase"
mv "$CAPTURE_DIR" "history/capture/$phase"
compose --profile burn down
wc -l "history/capture/$phase"/*.jsonl
