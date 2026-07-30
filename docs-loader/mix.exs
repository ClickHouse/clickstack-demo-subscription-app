defmodule DocsLoader.MixProject do
  use Mix.Project

  def project do
    [
      app: :docs_loader,
      version: "1.0.0",
      elixir: "~> 1.18",
      start_permanent: Mix.env() == :prod,
      deps: deps(),
      releases: releases()
    ]
  end

  def application do
    [
      extra_applications: [:logger, :inets, :ssl],
      mod: {DocsLoader.Application, []}
    ]
  end

  defp deps do
    [
      {:plug, "~> 1.16"},
      {:bandit, "~> 1.5"},
      {:jason, "~> 1.4"},
      {:opentelemetry, "~> 1.5"},
      {:opentelemetry_api, "~> 1.4"},
      {:opentelemetry_exporter, "~> 1.8"},
      {:opentelemetry_bandit, "~> 0.2"},
      {:opentelemetry_telemetry, "~> 1.1"}
    ]
  end

  defp releases do
    [
      docs_loader: [
        include_executables_for: [:unix],
        applications: [
          opentelemetry_exporter: :permanent,
          opentelemetry: :temporary,
          runtime_tools: :permanent
        ]
      ]
    ]
  end
end
