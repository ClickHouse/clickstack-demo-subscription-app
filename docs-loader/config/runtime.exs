import Config

# HTTP port (matches the Go service: PORT env, default 8001).
port =
  System.get_env("PORT", "8001")
  |> String.to_integer()

config :docs_loader, :port, port

# --- OpenTelemetry OTLP exporter configuration ---------------------------
#
# Honor the standard OTEL_* env vars set by docker-compose:
#   OTEL_EXPORTER_OTLP_ENDPOINT   e.g. http://clickstack:4318
#   OTEL_EXPORTER_OTLP_PROTOCOL   e.g. http/protobuf | grpc
#   OTEL_SERVICE_NAME             e.g. docs-loader
#   OTEL_EXPORTER_OTLP_HEADERS    e.g. authorization=<key>
#   OTEL_EXPORTER_OTLP_INSECURE   e.g. true (endpoint is plain http)

service_name = System.get_env("OTEL_SERVICE_NAME", "docs-loader")

config :opentelemetry, :resource,
  service: %{name: service_name},
  service_version: "1.0.0"

endpoint = System.get_env("OTEL_EXPORTER_OTLP_ENDPOINT")

protocol =
  case System.get_env("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf") do
    "grpc" -> :grpc
    _ -> :http_protobuf
  end

# Parse OTEL_EXPORTER_OTLP_HEADERS ("k1=v1,k2=v2") into a keyword-ish list of tuples.
headers =
  case System.get_env("OTEL_EXPORTER_OTLP_HEADERS") do
    nil ->
      []

    "" ->
      []

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

# OTEL_EXPORTER_OTLP_INSECURE=true => plain http, disable TLS verification.
insecure? =
  System.get_env("OTEL_EXPORTER_OTLP_INSECURE", "false")
  |> String.downcase()
  |> Kernel.in(["1", "true", "yes"])

if endpoint do
  otlp_opts =
    [
      protocol: protocol,
      endpoint: endpoint,
      headers: headers
    ]
    |> then(fn opts ->
      if insecure?, do: Keyword.put(opts, :ssl_options, []), else: opts
    end)

  config :opentelemetry_exporter, otlp_opts
end
