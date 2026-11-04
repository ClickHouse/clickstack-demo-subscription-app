#!/bin/sh
# Turn the standard OTel SDK variables, copied as-is from ClickHouse
# Observability, into the two values the collector config reads.
#   OTEL_EXPORTER_OTLP_ENDPOINT=https://...      -> OTLP_ENDPOINT
#   OTEL_EXPORTER_OTLP_HEADERS=authorization=... -> OTLP_AUTHORIZATION
# Header values may be percent-encoded, as the OTel spec allows.
set -e

if [ -n "$OTEL_EXPORTER_OTLP_ENDPOINT" ]; then
  export OTLP_ENDPOINT="${OTEL_EXPORTER_OTLP_ENDPOINT%/}"
fi

if [ -n "$OTEL_EXPORTER_OTLP_HEADERS" ]; then
  auth=$(printf '%s' "$OTEL_EXPORTER_OTLP_HEADERS" | tr ',' '\n' \
    | sed -n 's/^[[:space:]]*[Aa]uthorization[[:space:]]*=[[:space:]]*//p' | head -n 1)
  export OTLP_AUTHORIZATION=$(printf '%s' "$auth" | sed 's/%20/ /g')
fi

exec /otelcol-contrib "$@"
