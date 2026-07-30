defmodule SubscriptionApp.MixProject do
  use Mix.Project

  def project do
    [
      app: :subscription_app,
      version: "1.0.0",
      elixir: "~> 1.18",
      start_permanent: Mix.env() == :prod,
      deps: deps(),
      releases: releases()
    ]
  end

  def application do
    [
      extra_applications: [:logger],
      mod: {SubscriptionApp.Application, []}
    ]
  end

  defp deps do
    [
      {:plug, "~> 1.16"},
      {:bandit, "~> 1.6"},
      {:postgrex, "~> 0.19"},
      {:jason, "~> 1.4"},
      {:req, "~> 0.5"},
      {:opentelemetry, "~> 1.5"},
      {:opentelemetry_api, "~> 1.4"},
      {:opentelemetry_exporter, "~> 1.8"},
      {:opentelemetry_telemetry, "~> 1.1"},
      {:opentelemetry_bandit, "~> 0.2"}
    ]
  end

  defp releases do
    [
      subscription_app: [
        include_executables_for: [:unix],
        applications: [runtime_tools: :permanent]
      ]
    ]
  end
end
