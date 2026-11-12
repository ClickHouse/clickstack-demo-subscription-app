FROM golang:1.26-bookworm AS builder

WORKDIR /app

COPY ./go.mod go.mod

COPY ./healthcheck.go healthcheck.go

RUN CGO_ENABLED=0 GOOS=linux go build -ldflags "-s -w" -o healthcheck healthcheck.go

# Pinned. The agent configs batch in the exporter (sending_queue.batch) and use
# the otlp_http / otlp_grpc exporter names, which need 0.144.0 or later. The
# batch processor is deprecated and is removed in 0.177.0.
FROM otel/opentelemetry-collector-contrib:0.165.0 AS otelcol

# The contrib image has no shell, and entrypoint.sh needs one to read the
# standard OTEL_EXPORTER_OTLP_* variables, so the binary moves onto Alpine.
FROM alpine:3.22

COPY --from=otelcol /otelcol-contrib /otelcol-contrib
COPY --from=builder /app/healthcheck ./
COPY ./entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["--config", "/etc/otelcol-contrib/config.yaml"]
