defmodule DocsLoader.OtelLogHandler do
  @moduledoc """
  A `:logger` handler that exports log events as OpenTelemetry log records over
  OTLP/HTTP (JSON) to the collector's `/v1/logs` endpoint.

  The official `opentelemetry_exporter` (as of v1.9) only exports traces, so the
  original Go service's OTLP log pipeline (otelzap + otlplogs) is reproduced here
  with a small hand-rolled exporter. Records include `service.name` and, when a
  span is active, the trace/span id for correlation.

  Requests are fired from a throwaway process so logging never blocks the caller,
  and events originating from the HTTP/TLS stack (or this module) are dropped to
  avoid a feedback loop when the collector is unreachable.
  """

  # Elixir Logger level => {OTLP severityNumber, severityText}
  @severity %{
    debug: {5, "DEBUG"},
    info: {9, "INFO"},
    notice: {10, "INFO2"},
    warning: {13, "WARN"},
    warn: {13, "WARN"},
    error: {17, "ERROR"},
    critical: {18, "ERROR2"},
    alert: {19, "ERROR3"},
    emergency: {21, "FATAL"}
  }

  # ---- :logger handler callback --------------------------------------------
  def log(%{level: level, msg: msg, meta: meta}, %{config: cfg}) do
    unless internal?(meta) do
      record = build_record(level, msg, meta)
      ship(envelope(record, cfg), cfg)
    end

    :ok
  end

  def log(_event, _config), do: :ok

  # ---- Record construction --------------------------------------------------
  defp build_record(level, msg, meta) do
    {sev_num, sev_text} = Map.get(@severity, level, {9, "INFO"})
    time_ns = (meta[:time] || :os.system_time(:microsecond)) * 1000

    %{
      "timeUnixNano" => Integer.to_string(time_ns),
      "observedTimeUnixNano" => Integer.to_string(time_ns),
      "severityNumber" => sev_num,
      "severityText" => sev_text,
      "body" => %{"stringValue" => message_to_string(msg)}
    }
    |> put_trace_context()
  end

  # Best-effort trace/span correlation from the active OpenTelemetry span.
  defp put_trace_context(record) do
    case current_ids() do
      {trace_id, span_id} when is_binary(trace_id) and is_binary(span_id) ->
        Map.merge(record, %{"traceId" => trace_id, "spanId" => span_id})

      _ ->
        record
    end
  rescue
    _ -> record
  catch
    _, _ -> record
  end

  defp current_ids do
    ctx = :otel_tracer.current_span_ctx()

    trace_id = :otel_span.trace_id(ctx)
    span_id = :otel_span.span_id(ctx)

    if is_integer(trace_id) and trace_id != 0 do
      {hex(trace_id, 16), hex(span_id, 8)}
    else
      {nil, nil}
    end
  end

  defp hex(int, bytes) do
    int
    |> :binary.encode_unsigned()
    |> pad_leading(bytes)
    |> Base.encode16(case: :lower)
  end

  defp pad_leading(bin, bytes) when byte_size(bin) < bytes,
    do: pad_leading(<<0>> <> bin, bytes)

  defp pad_leading(bin, _bytes), do: bin

  defp message_to_string({:string, chardata}), do: IO.chardata_to_string(chardata)

  defp message_to_string({:report, report}), do: inspect(report)

  defp message_to_string({format, args}) when is_list(args) do
    :io_lib.format(format, args) |> IO.chardata_to_string()
  rescue
    _ -> inspect({format, args})
  end

  defp message_to_string(other), do: inspect(other)

  # ---- OTLP envelope + transport -------------------------------------------
  defp envelope(record, cfg) do
    %{
      "resourceLogs" => [
        %{
          "resource" => %{
            "attributes" => [
              %{"key" => "service.name", "value" => %{"stringValue" => cfg.service_name}}
            ]
          },
          "scopeLogs" => [
            %{"scope" => %{"name" => cfg.scope}, "logRecords" => [record]}
          ]
        }
      ]
    }
  end

  defp ship(payload, cfg) do
    body = Jason.encode!(payload)
    url = String.to_charlist(cfg.logs_url)
    headers = cfg.http_headers

    spawn(fn ->
      :httpc.request(
        :post,
        {url, headers, ~c"application/json", body},
        [{:timeout, 2000}, {:connect_timeout, 2000}],
        [{:body_format, :binary}]
      )
    end)

    :ok
  end

  # Drop events emitted by the HTTP/TLS stack or this module to avoid a
  # feedback loop (e.g. when the collector is unreachable).
  defp internal?(meta) do
    case meta[:mfa] do
      {mod, _fun, _arity} ->
        name = Atom.to_string(mod)

        String.starts_with?(name, "httpc") or
          String.starts_with?(name, "inets") or
          String.starts_with?(name, "Elixir.DocsLoader.OtelLogHandler") or
          name in ["ssl", "tls_connection", "tls_dyn_connection", "ssl_connection"]

      _ ->
        false
    end
  end
end
