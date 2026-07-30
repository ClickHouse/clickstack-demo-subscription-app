defmodule DocsLoader.Application do
  @moduledoc false

  use Application
  require Logger

  @impl true
  def start(_type, _args) do
    port = Application.get_env(:docs_loader, :port, 8001)

    # Register Bandit telemetry -> OpenTelemetry span bridge.
    OpentelemetryBandit.setup()

    # Export Logger events as OTLP logs (mirrors the original otelzap pipeline).
    setup_otel_logs()

    children = [
      {Bandit, plug: DocsLoader.Router, scheme: :http, ip: {0, 0, 0, 0}, port: port}
    ]

    Logger.info("** Service Started on Port #{port} **")

    opts = [strategy: :one_for_one, name: DocsLoader.Supervisor]
    Supervisor.start_link(children, opts)
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
