defmodule DocsLoader.Application do
  @moduledoc false

  use Application
  require Logger

  @impl true
  def start(_type, _args) do
    port = Application.get_env(:docs_loader, :port, 8001)

    # Register Bandit telemetry -> OpenTelemetry span bridge.
    OpentelemetryBandit.setup()

    children = [
      {Bandit, plug: DocsLoader.Router, scheme: :http, ip: {0, 0, 0, 0}, port: port}
    ]

    Logger.info("** Service Started on Port #{port} **")

    opts = [strategy: :one_for_one, name: DocsLoader.Supervisor]
    Supervisor.start_link(children, opts)
  end
end
