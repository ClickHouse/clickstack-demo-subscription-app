defmodule SubscriptionApp.Router do
  @moduledoc """
  HTTP routes mirroring the original Flask service, byte-for-byte on external
  behavior (paths, methods, status codes, JSON shapes).
  """

  use Plug.Router
  require Logger
  require OpenTelemetry.Tracer

  plug(:match)

  # Access log at INFO for every request (mirrors the Flask log_request()
  # INFO line, which the original service shipped to ClickStack over OTLP).
  plug(:access_log)

  plug(Plug.Parsers,
    parsers: [:json],
    pass: ["application/json"],
    json_decoder: Jason
  )

  plug(:dispatch)

  defp access_log(conn, _opts) do
    start = System.monotonic_time()

    client_ip =
      case get_req_header(conn, "x-forwarded-for") do
        [xff | _] -> xff
        _ -> conn.remote_ip |> :inet.ntoa() |> to_string()
      end

    user_agent = conn |> get_req_header("user-agent") |> List.first() || "-"

    register_before_send(conn, fn conn ->
      duration_ms =
        System.convert_time_unit(System.monotonic_time() - start, :native, :millisecond)

      Logger.info(
        ~s(#{client_ip} "#{conn.method} #{conn.request_path}" #{conn.status} #{duration_ms}ms "#{user_agent}")
      )

      conn
    end)
  end

  # ---------------------------------------------------------------------------
  # GET / -> rendered HTML page with injected HyperDX config
  # ---------------------------------------------------------------------------
  get "/" do
    Logger.debug("Serving main page")

    conn
    |> put_resp_content_type("text/html")
    |> send_resp(200, SubscriptionApp.Template.index())
  end

  # ---------------------------------------------------------------------------
  # POST /api/subscribe
  # ---------------------------------------------------------------------------
  post "/api/subscribe" do
    Logger.debug("Processing subscription request")
    data = conn.body_params || %{}

    with :ok <- validate(data, "name"),
         :ok <- validate(data, "email"),
         :ok <- validate(data, "source") do
      params = [
        data |> Map.get("name", "") |> to_string() |> String.trim(),
        data |> Map.get("company", "") |> to_string() |> String.trim(),
        data |> Map.get("email", "") |> to_string() |> String.trim() |> String.downcase(),
        data |> Map.get("source", "") |> to_string() |> String.trim(),
        DateTime.utc_now()
      ]

      insert_query = """
      INSERT INTO users (name, company, email, source, submitted_at)
      VALUES ($1, $2, $3, $4, $5)
      ON CONFLICT (email) DO UPDATE SET
          name = EXCLUDED.name,
          company = EXCLUDED.company,
          source = EXCLUDED.source,
          submitted_at = EXCLUDED.submitted_at;
      """

      case db_query("INSERT users", "INSERT", insert_query, params) do
        {:ok, _result} ->
          send_json(conn, 200, %{
            success: true,
            message: "Successfully subscribed to updates!"
          })

        {:error, %DBConnection.ConnectionError{} = err} ->
          Logger.error("Database connection failed during subscription: #{inspect(err)}")

          send_json(conn, 500, %{
            success: false,
            error: "Database connection failed"
          })

        {:error, err} ->
          Logger.error("Error processing subscription: #{inspect(err)}")

          send_json(conn, 500, %{
            success: false,
            error: "An error occurred while processing your subscription"
          })
      end
    else
      {:missing, field} ->
        Logger.warning("Missing required field: #{field}")
        send_json(conn, 400, %{success: false, error: "Missing required field: #{field}"})
    end
  end

  # ---------------------------------------------------------------------------
  # GET /load-docs -> proxy to docs-loader /load
  # ---------------------------------------------------------------------------
  get "/load-docs" do
    Logger.debug("Simulate loading docs")

    host = Application.get_env(:subscription_app, :docs_loader_host, "localhost")
    port = Application.get_env(:subscription_app, :docs_loader_port, 8001)
    url = "http://#{host}:#{port}/load"

    case proxy_get(url, host, port) do
      {:ok, %Req.Response{status: status, body: body}} when status >= 200 and status < 400 ->
        send_json(conn, 200, body)

      {:ok, %Req.Response{status: status}} ->
        send_json(conn, 500, %{error: "HTTP #{status} error for url: #{url}"})

      {:error, err} ->
        send_json(conn, 500, %{error: Exception.message(err)})
    end
  end

  # ---------------------------------------------------------------------------
  # GET /health -> SELECT 1
  # ---------------------------------------------------------------------------
  get "/health" do
    Logger.debug("Health check requested")

    now = DateTime.utc_now() |> DateTime.to_iso8601()

    case db_query("SELECT", "SELECT", "SELECT 1;", []) do
      {:ok, _} ->
        send_json(conn, 200, %{
          status: "healthy",
          database: "connected",
          timestamp: now
        })

      {:error, %DBConnection.ConnectionError{}} ->
        Logger.error("Health check failed - database disconnected")

        send_json(conn, 503, %{
          status: "unhealthy",
          database: "disconnected",
          timestamp: now
        })

      {:error, err} ->
        Logger.error("Health check failed with error: #{inspect(err)}")

        send_json(conn, 503, %{
          status: "unhealthy",
          error: inspect(err),
          timestamp: now
        })
    end
  end

  # ---------------------------------------------------------------------------
  # Static file routes
  # ---------------------------------------------------------------------------
  get "/css/:filename", do: serve_static(conn, "css", filename)
  get "/js/:filename", do: serve_static(conn, "js", filename)
  get "/images/:filename", do: serve_static(conn, "images", filename)

  match _ do
    send_json(conn, 404, %{error: "Not Found"})
  end

  # ---------------------------------------------------------------------------
  # Helpers
  # ---------------------------------------------------------------------------

  # Run a Postgrex query inside a client span, mirroring the DB-query spans the
  # original Flask app got from opentelemetry-instrumentation-psycopg2.
  defp db_query(span_name, operation, statement, params) do
    OpenTelemetry.Tracer.with_span span_name, %{
      kind: :client,
      attributes: %{
        "db.system" => "postgresql",
        "db.operation" => operation,
        "db.statement" => statement,
        "db.name" => db_name()
      }
    } do
      Postgrex.query(SubscriptionApp.Repo, statement, params)
    end
  end

  defp db_name do
    Application.get_env(:subscription_app, SubscriptionApp.Repo, [])
    |> Keyword.get(:database, "postgres")
  end

  # Outbound HTTP call inside a client span, mirroring the spans the original
  # Flask app got from opentelemetry-instrumentation-requests.
  defp proxy_get(url, host, port) do
    OpenTelemetry.Tracer.with_span "GET", %{
      kind: :client,
      attributes: %{
        "http.request.method" => "GET",
        "url.full" => url,
        "server.address" => host,
        "server.port" => port
      }
    } do
      case Req.get(url) do
        {:ok, %Req.Response{status: status}} = ok ->
          OpenTelemetry.Tracer.set_attribute("http.response.status_code", status)
          ok

        {:error, err} = error ->
          OpenTelemetry.Tracer.set_attributes(%{
            "error" => true,
            "exception.message" => Exception.message(err)
          })

          error
      end
    end
  end

  defp validate(data, field) do
    case Map.get(data, field) do
      nil -> {:missing, field}
      "" -> {:missing, field}
      value when is_binary(value) -> if String.trim(value) == "", do: {:missing, field}, else: :ok
      _ -> :ok
    end
  end

  defp send_json(conn, status, body) do
    conn
    |> put_resp_content_type("application/json")
    |> send_resp(status, Jason.encode!(body))
  end

  defp serve_static(conn, subdir, filename) do
    base = Path.join([:code.priv_dir(:subscription_app), "static", subdir])
    # Prevent path traversal; only serve a plain filename.
    safe = Path.basename(filename)
    path = Path.join(base, safe)

    if File.regular?(path) do
      content_type = MIME.from_path(safe)

      conn
      |> put_resp_content_type(content_type)
      |> send_file(200, path)
    else
      send_json(conn, 404, %{error: "Not Found"})
    end
  end
end
