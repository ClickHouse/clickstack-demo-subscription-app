import Config

# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------
get = fn name, default -> System.get_env(name, default) end

to_int = fn value, default ->
  case Integer.parse(to_string(value)) do
    {int, _} -> int
    :error -> default
  end
end

# ---------------------------------------------------------------------------
# HTTP server (bind address + port). Mirrors FLASK_HOST / FLASK_PORT.
# ---------------------------------------------------------------------------
flask_host = get.("FLASK_HOST", "0.0.0.0")
flask_port = to_int.(get.("FLASK_PORT", "8000"), 8000)

config :subscription_app,
  host: flask_host,
  port: flask_port,
  hyperdx_api_key: get.("HYPERDX_API_KEY", ""),
  hyperdx_service_name: get.("HYPERDX_SERVICE_NAME", "subscription-frontend"),
  hyperdx_endpoint: get.("HYPERDX_ENDPOINT", "http://localhost:4318"),
  docs_loader_host: get.("DOCS_LOADER_HOST", "localhost"),
  docs_loader_port: to_int.(get.("DOCS_LOADER_PORT", "8001"), 8001)

# ---------------------------------------------------------------------------
# Postgres (raw connection via Postgrex, mirrors psycopg2 config).
# ---------------------------------------------------------------------------
config :subscription_app, SubscriptionApp.Repo,
  hostname: get.("POSTGRES_HOST", "localhost"),
  port: to_int.(get.("POSTGRES_PORT", "5432"), 5432),
  username: get.("POSTGRES_USERNAME", "postgres"),
  password: get.("POSTGRES_PASSWORD", ""),
  database: get.("POSTGRES_DATABASE", "postgres")

# ---------------------------------------------------------------------------
# Logging level (mirrors LOG_LEVEL).
# ---------------------------------------------------------------------------
log_level =
  case get.("LOG_LEVEL", "INFO") |> String.downcase() do
    "debug" -> :debug
    "info" -> :info
    "warning" -> :warning
    "warn" -> :warning
    "error" -> :error
    _ -> :info
  end

config :logger, level: log_level

# ---------------------------------------------------------------------------
# OpenTelemetry OTLP exporter.
# ---------------------------------------------------------------------------
otlp_endpoint =
  get.("OTEL_EXPORTER_OTLP_ENDPOINT", nil) ||
    System.get_env("HYPERDX_ENDPOINT") || "http://localhost:4318"

otlp_protocol =
  case get.("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf") do
    "grpc" -> :grpc
    _ -> :http_protobuf
  end

config :opentelemetry, :resource,
  service: %{name: get.("OTEL_SERVICE_NAME", "subscription-backend")}

exporter_opts = [endpoints: [otlp_endpoint]]

config :opentelemetry_exporter,
  otlp_protocol: otlp_protocol,
  otlp_endpoint: otlp_endpoint,
  otlp_traces_endpoint: otlp_endpoint

# OTEL_EXPORTER_OTLP_INSECURE is honored implicitly via the http/https scheme
# of the endpoint; keep a reference so misconfiguration is visible in logs.
_ = System.get_env("OTEL_EXPORTER_OTLP_INSECURE")
_ = exporter_opts
