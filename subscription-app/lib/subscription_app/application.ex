defmodule SubscriptionApp.Application do
  @moduledoc false

  use Application
  require Logger

  @impl true
  def start(_type, _args) do
    # Auto-instrument Bandit HTTP spans.
    _ = OpentelemetryBandit.setup()

    # Name server spans "{METHOD} {route}" (e.g. "POST /api/subscribe") instead
    # of the bare method Bandit emits, using Plug's matched route template.
    setup_span_naming()

    # Export Logger events as OTLP logs (mirrors the original Flask logging
    # instrumentation, which the trace-only opentelemetry_exporter cannot do).
    setup_otel_logs()

    port = Application.get_env(:subscription_app, :port, 8000)
    host = Application.get_env(:subscription_app, :host, "0.0.0.0")

    children = [
      # Raw Postgres connection (Postgrex, no Ecto). Started supervised so it
      # tolerates the DB not being immediately available and retries.
      Supervisor.child_spec(
        {Postgrex,
         Keyword.merge(
           Application.get_env(:subscription_app, SubscriptionApp.Repo, []),
           name: SubscriptionApp.Repo
         )},
        id: SubscriptionApp.Repo
      ),
      {Bandit, plug: SubscriptionApp.Router, ip: parse_ip(host), port: port}
    ]

    Logger.info("Starting subscription application on #{host}:#{port}...")

    opts = [strategy: :one_for_one, name: SubscriptionApp.Supervisor]
    Supervisor.start_link(children, opts)
  end

  defp setup_span_naming do
    :telemetry.attach(
      "otel-span-route-name",
      [:plug, :router_dispatch, :start],
      &__MODULE__.rename_span/4,
      nil
    )
  end

  # Runs in the request process, so the current span is the Bandit server span.
  def rename_span(_event, _measurements, %{conn: conn, route: route}, _config) do
    ctx = :otel_tracer.current_span_ctx()
    :otel_span.update_name(ctx, "#{conn.method} #{route}")
    :otel_span.set_attribute(ctx, "http.route", route)
    :ok
  rescue
    _ -> :ok
  catch
    _, _ -> :ok
  end

  defp setup_otel_logs do
    cfg = Application.get_env(:subscription_app, :otel_logs, [])

    if cfg[:enabled] do
      :logger.add_handler(:otlp_logs, SubscriptionApp.OtelLogHandler, %{
        level: cfg[:level] || :info,
        config: %{
          service_name: cfg[:service_name],
          scope: "subscription_app",
          logs_url: cfg[:logs_url],
          http_headers: cfg[:http_headers]
        }
      })

      Logger.info("OTLP log export enabled -> #{cfg[:logs_url]}")
    end
  end

  # Convert a bind address string into a tuple Bandit/Thousand Island accepts.
  defp parse_ip("0.0.0.0"), do: {0, 0, 0, 0}
  defp parse_ip(host) when is_binary(host) do
    case :inet.parse_address(String.to_charlist(host)) do
      {:ok, ip} -> ip
      _ -> {0, 0, 0, 0}
    end
  end
end
