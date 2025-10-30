FROM golang:1.25-bookworm AS builder

WORKDIR /app

COPY ./go.mod go.mod

COPY ./healthcheck.go healthcheck.go

RUN CGO_ENABLED=0 GOOS=linux go build -ldflags "-s -w" -o healthcheck healthcheck.go

FROM otel/opentelemetry-collector-contrib:latest

COPY --from=builder /app/healthcheck ./
