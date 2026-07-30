import Config

config :logger, :console,
  format: "$time [$level] $message\n"

# OpenTelemetry: configure the exporter to use OTLP. Concrete endpoint/protocol
# are supplied at runtime (config/runtime.exs) from environment variables.
config :opentelemetry,
  span_processor: :batch,
  traces_exporter: :otlp
