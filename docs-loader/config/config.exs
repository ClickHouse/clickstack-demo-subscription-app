import Config

# Ensure OpenTelemetry spans are exported through the OTLP exporter.
# The exporter itself is configured at runtime in runtime.exs from env vars.
config :opentelemetry,
  span_processor: :batch,
  traces_exporter: :otlp

# Enable Bandit auto-instrumentation (HTTP server spans) via opentelemetry_bandit.
config :opentelemetry_bandit, enabled: true
