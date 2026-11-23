package main

import (
  "context"
  "errors"
  "io"
  "log"
  "net/http"
  "os"
  "time"

  "go.opentelemetry.io/contrib/bridges/otelzap"
  "go.opentelemetry.io/contrib/instrumentation/host"
  "go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
  "go.opentelemetry.io/contrib/instrumentation/runtime"
  "go.opentelemetry.io/otel"
  "go.opentelemetry.io/otel/exporters/otlp/otlplog/otlploghttp"
  "go.opentelemetry.io/otel/exporters/otlp/otlpmetric/otlpmetrichttp"
  "go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
  "go.opentelemetry.io/otel/log/global"
  "go.opentelemetry.io/otel/propagation"
  sdklog "go.opentelemetry.io/otel/sdk/log"
  sdkmetric "go.opentelemetry.io/otel/sdk/metric"
  "go.opentelemetry.io/otel/sdk/resource"
  sdktrace "go.opentelemetry.io/otel/sdk/trace"
  "go.uber.org/zap"
)

// setupOpenTelemetry configures traces, metrics, and logs with the upstream
// OpenTelemetry SDK. Everything is read from the standard OTEL_* environment
// variables: OTEL_EXPORTER_OTLP_ENDPOINT, OTEL_EXPORTER_OTLP_HEADERS,
// OTEL_SERVICE_NAME and OTEL_RESOURCE_ATTRIBUTES (for service.version).
func setupOpenTelemetry(ctx context.Context) (shutdown func(context.Context) error, err error) {
  var shutdowns []func(context.Context) error
  shutdown = func(ctx context.Context) error {
    var errs error
    for _, fn := range shutdowns {
      errs = errors.Join(errs, fn(ctx))
    }
    return errs
  }

  res, err := resource.New(ctx,
    resource.WithFromEnv(),
    resource.WithTelemetrySDK(),
    resource.WithHost(),
    resource.WithProcess(),
  )
  if err != nil {
    return shutdown, err
  }

  otel.SetTextMapPropagator(propagation.NewCompositeTextMapPropagator(
    propagation.TraceContext{}, propagation.Baggage{}))

  traceExporter, err := otlptracehttp.New(ctx)
  if err != nil {
    return shutdown, err
  }
  tracerProvider := sdktrace.NewTracerProvider(
    sdktrace.WithBatcher(traceExporter),
    sdktrace.WithResource(res),
  )
  shutdowns = append(shutdowns, tracerProvider.Shutdown)
  otel.SetTracerProvider(tracerProvider)

  metricExporter, err := otlpmetrichttp.New(ctx)
  if err != nil {
    return shutdown, err
  }
  meterProvider := sdkmetric.NewMeterProvider(
    sdkmetric.WithReader(sdkmetric.NewPeriodicReader(metricExporter)),
    sdkmetric.WithResource(res),
  )
  shutdowns = append(shutdowns, meterProvider.Shutdown)
  otel.SetMeterProvider(meterProvider)

  // Go runtime (memory, GC, goroutines) and host (CPU, memory, network) metrics
  if err := runtime.Start(); err != nil {
    return shutdown, err
  }
  if err := host.Start(); err != nil {
    return shutdown, err
  }

  logExporter, err := otlploghttp.New(ctx)
  if err != nil {
    return shutdown, err
  }
  loggerProvider := sdklog.NewLoggerProvider(
    sdklog.WithProcessor(sdklog.NewBatchProcessor(logExporter)),
    sdklog.WithResource(res),
  )
  shutdowns = append(shutdowns, loggerProvider.Shutdown)
  global.SetLoggerProvider(loggerProvider)

  return shutdown, nil
}

func main() {
  ctx := context.Background()

  otelShutdown, err := setupOpenTelemetry(ctx)
  if err != nil {
    log.Fatalf("error setting up OpenTelemetry: %v", err)
  }
  // gracefully shut down to flush accumulated signals before the program ends
  defer otelShutdown(ctx)

  // zap logger whose records go to OpenTelemetry, and set it globally
  logger := zap.New(otelzap.NewCore("docs-loader"))
  zap.ReplaceGlobals(logger)

  http.Handle("/", otelhttp.NewHandler(wrapHandler(logger, Status), "/"))
  http.Handle("/load", otelhttp.NewHandler(wrapHandler(logger, Load), "/load"))

  port := os.Getenv("PORT")
  if port == "" {
    port = "8001"
  }

  logger.Info("** Service Started on Port " + port + " **")
  if err := http.ListenAndServe(":"+port, nil); err != nil {
    logger.Fatal(err.Error())
  }
}

// Use this to wrap all handlers so their logs carry the request's trace context
func wrapHandler(logger *zap.Logger, handler http.HandlerFunc) http.HandlerFunc {
  return func(w http.ResponseWriter, r *http.Request) {
    // otelzap reads the trace and span IDs from a context.Context field
    ctx := zap.Any("ctx", r.Context())
    logger.Info("request received: "+r.Method+" "+r.URL.Path, ctx, zap.String("url", r.URL.Path), zap.String("method", r.Method))
    handler(w, r)
    logger.Info("request completed: "+r.Method+" "+r.URL.Path, ctx, zap.String("path", r.URL.Path), zap.String("method", r.Method))
  }
}

func Status(w http.ResponseWriter, r *http.Request) {
  w.Header().Add("Content-Type", "application/json")
  io.WriteString(w, `{"status":"ok"}`)
}

func Load(w http.ResponseWriter, r *http.Request) {
  var data [][]byte
  chunkSize := 1024 * 1024 // 1 MB

  for i := 0; ; i++ {
    // Allocate a new byte slice of chunkSize
    chunk := make([]byte, chunkSize)

    // Append it to the data slice, continuously increasing memory usage
    data = append(data, chunk)

    // Introduce a small delay to observe memory growth more clearly
    time.Sleep(10 * time.Millisecond)
  }

  w.Header().Add("Content-Type", "application/json")
  io.WriteString(w, `{"status":"ok"}`)
}
