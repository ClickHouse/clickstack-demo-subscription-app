defmodule DocsLoader.Router do
  @moduledoc """
  HTTP routes mirroring the original Go docs-loader service.

    * `GET /`     -> health/status endpoint returning `{"status":"ok"}`
    * `GET /load` -> deliberate unbounded memory-growth simulation
  """

  use Plug.Router
  require Logger

  # 1 MB per chunk, matching the Go implementation.
  @chunk_size 1024 * 1024

  plug(:match)
  plug(:dispatch)

  # Status / health endpoint. Handle HEAD as well as GET: the compose
  # healthcheck uses `wget --spider`, which issues a HEAD request, and the
  # original Go server answered HEAD automatically.
  match "/", via: [:get, :head] do
    conn
    |> put_resp_content_type("application/json")
    |> send_resp(200, ~s({"status":"ok"}))
  end

  # Memory-growth simulation: allocate 1 MB binaries in a loop, retaining
  # references so the BEAM can never garbage-collect them. This grows the
  # process memory without bound until the container hits its memory limit
  # and is OOM-killed. It intentionally never sends a normal response.
  get "/load" do
    Logger.info("request received: GET /load")
    leak([], 0)
    # Unreachable in practice.
    send_resp(conn, 200, ~s({"status":"ok"}))
  end

  match _ do
    send_resp(conn, 404, ~s({"status":"not found"}))
  end

  # Retain every allocated chunk by accumulating them in `acc`, which stays
  # live on the stack across every iteration, defeating garbage collection.
  defp leak(acc, i) do
    chunk = :binary.copy(<<0>>, @chunk_size)
    acc = [chunk | acc]
    Process.sleep(10)
    leak(acc, i + 1)
  end
end
