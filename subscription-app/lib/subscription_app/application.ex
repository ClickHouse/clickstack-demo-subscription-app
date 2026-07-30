defmodule SubscriptionApp.Application do
  @moduledoc false

  use Application
  require Logger

  @impl true
  def start(_type, _args) do
    # Auto-instrument Bandit HTTP spans.
    _ = OpentelemetryBandit.setup()

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
