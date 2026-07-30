defmodule SubscriptionApp.Template do
  @moduledoc """
  Compiles the index EEx template at build time and renders it with the
  HyperDX config injected from environment-derived application config.
  """

  require EEx

  @template_path Path.join([:code.priv_dir(:subscription_app), "templates", "index.html.eex"])
  @external_resource @template_path

  EEx.function_from_file(:def, :render_index, @template_path, [:hyperdx_config])

  @doc "Renders the index page, injecting the HyperDX config JSON."
  def index do
    config = %{
      "api_key" => Application.get_env(:subscription_app, :hyperdx_api_key, ""),
      "service_name" =>
        Application.get_env(:subscription_app, :hyperdx_service_name, "subscription-frontend"),
      "endpoint" =>
        Application.get_env(:subscription_app, :hyperdx_endpoint, "http://localhost:4318")
    }

    render_index(Jason.encode!(config))
  end
end
