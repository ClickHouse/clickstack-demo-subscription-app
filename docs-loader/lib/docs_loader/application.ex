defmodule DocsLoader.Application do
  @moduledoc false

  use Application
  require Logger

  @impl true
  def start(_type, _args) do
    port = Application.get_env(:docs_loader, :port, 8001)

    # Register Bandit telemetry -> OpenTelemetry span bridge.
    OpentelemetryBandit.setup()

    # Name server spans "{METHOD} {route}" instead of the bare method Bandit
    # emits, using Plug's matched route template.
    setup_span_naming()

    # Export Logger events as OTLP logs (mirrors the original otelzap pipeline).
    setup_otel_logs()

    children = [
      {Bandit, plug: DocsLoader.Router, scheme: :http, ip: {0, 0, 0, 0}, port: port}
    ]

    Logger.info("** Service Started on Port #{port} **")

    opts = [strategy: :one_for_one, name: DocsLoader.Supervisor]
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
    cfg = Application.get_env(:docs_loader, :otel_logs, [])

    if cfg[:enabled] do
      :httpc.set_options(pipeline_timeout: 2000)

      :logger.add_handler(:otlp_logs, DocsLoader.OtelLogHandler, %{
        level: cfg[:level] || :info,
        config: %{
          service_name: cfg[:service_name],
          scope: "docs_loader",
          logs_url: cfg[:logs_url],
          http_headers: cfg[:http_headers]
        }
      })

      Logger.info("OTLP log export enabled -> #{cfg[:logs_url]}")
    end
  end
end
