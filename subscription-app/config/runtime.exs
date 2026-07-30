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

# Authorization/headers for OTLP export. ClickStack rejects exports without an
# authorization header (HTTP 401). Take OTEL_EXPORTER_OTLP_HEADERS if set,
# otherwise fall back to HYPERDX_API_KEY as authorization (as the original
# HyperDX SDK did). Kept as {binary, binary} pairs for opentelemetry_exporter.
otlp_header_pairs =
  case get.("OTEL_EXPORTER_OTLP_HEADERS", "") do
    "" ->
      case get.("HYPERDX_API_KEY", "") do
        "" -> []
        key -> [{"authorization", key}]
      end

    raw ->
      raw
      |> String.split(",", trim: true)
      |> Enum.flat_map(fn pair ->
        case String.split(pair, "=", parts: 2) do
          [k, v] -> [{String.trim(k), String.trim(v)}]
          _ -> []
        end
      end)
  end

# Note: set only otlp_endpoint (the base). The exporter appends the signal
# path (/v1/traces). Setting otlp_traces_endpoint would be treated as the exact
# path and send spans to "/" instead.
config :opentelemetry_exporter,
  otlp_protocol: otlp_protocol,
  otlp_endpoint: otlp_endpoint,
  otlp_headers: otlp_header_pairs

# OTEL_EXPORTER_OTLP_INSECURE is honored implicitly via the http/https scheme
# of the endpoint; keep a reference so misconfiguration is visible in logs.
_ = System.get_env("OTEL_EXPORTER_OTLP_INSECURE")

# ---------------------------------------------------------------------------
# OTLP logs export.
#
# The opentelemetry_exporter only ships traces, so logs are exported by a small
# custom :logger handler (SubscriptionApp.OtelLogHandler) that POSTs OTLP JSON
# to <endpoint>/v1/logs. The authorization header comes from
# OTEL_EXPORTER_OTLP_HEADERS if set, else from HYPERDX_API_KEY (as the original
# HyperDX SDK did).
# ---------------------------------------------------------------------------
# :httpc wants charlist header tuples; reuse the pairs parsed for the exporter.
log_headers =
  Enum.map(otlp_header_pairs, fn {k, v} ->
    {String.to_charlist(k), String.to_charlist(v)}
  end)

config :subscription_app, :otel_logs,
  enabled: true,
  service_name: get.("OTEL_SERVICE_NAME", "subscription-backend"),
  logs_url: String.trim_trailing(otlp_endpoint, "/") <> "/v1/logs",
  http_headers: log_headers,
  level: log_level
