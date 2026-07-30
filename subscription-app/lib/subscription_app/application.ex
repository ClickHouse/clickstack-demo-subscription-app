defmodule SubscriptionApp.Application do
  @moduledoc false

  use Application
  require Logger

  @impl true
  def start(_type, _args) do
    # Auto-instrument Bandit HTTP spans.
    _ = OpentelemetryBandit.setup()

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

  # Convert a bind address string into a tuple Bandit/Thousand Island accepts.
  defp parse_ip("0.0.0.0"), do: {0, 0, 0, 0}
  defp parse_ip(host) when is_binary(host) do
    case :inet.parse_address(String.to_charlist(host)) do
      {:ok, ip} -> ip
      _ -> {0, 0, 0, 0}
    end
  end
end
