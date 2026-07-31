# Kubernetes deployment

A Kubernetes port of the docker-compose stack, as raw manifests wired
together with [Kustomize](https://kustomize.io/).

Everything runs in the `clickstack-demo` namespace.

## What's here

| File | Resource(s) |
|------|-------------|
| `namespace.yaml` | `clickstack-demo` namespace |
| `clickstack.yaml` | ClickStack OTel collector (OTLP ingest gateway → ClickHouse Cloud) + Service |
| `postgres.yaml` | Postgres Deployment, Service, PVC, and the `init.sql` ConfigMap |
| `subscription-app.yaml` | Flask app Deployment + ClusterIP Service (`8000`) |
| `docs-loader.yaml` | Go docs-loader Deployment + Service |
| `load-generator.yaml` | Locust load generator Deployment |
| `otel-collector.yaml` | Infra-metrics collector (kubeletstats + k8s_cluster) with ServiceAccount + RBAC |
| `kustomization.yaml` | Ties it together + generates the `clickstack-secrets` Secret |

### Differences from docker-compose

- **Infra metrics:** docker-compose used `socat` + the `docker_stats`
  receiver to read the Docker socket. Kubernetes has no Docker socket, so the
  `otel-collector` here uses the K8s-native **`kubeletstats`** and
  **`k8s_cluster`** receivers instead (with a ServiceAccount + ClusterRole).
  The `socat` service is gone.
- The subscription app is reached via `kubectl port-forward` rather than a
  published host port.
- Credentials come from a Kustomize-generated Secret (`k8s/secret.env`) instead
  of the repo-root `.env`. This keeps `k8s/` self-contained — kustomize cannot
  read files above its own directory, so pointing at `../.env` would force
  `--load-restrictor LoadRestrictionsNone` onto every command. It's the same
  four keys, so `cp ../.env secret.env` works if you already ran compose.

## Quick Start

1. **Create a ClickHouse Cloud service**
    - https://console.clickhouse.cloud

2. **Clone the repo**
   ```bash
   git clone https://github.com/ClickHouse/clickstack-demo-subscription-app
   ```

3. **Access the k8s directory**
   ```bash
   cd clickstack-demo-subscription-app/k8s
   ```

4. **Create a secret.env file**
   ```bash
   CLICKHOUSE_ENDPOINT=<HOST-WITH-PORT>
   CLICKHOUSE_USER=default
   CLICKHOUSE_PASSWORD=<PASSWORD>
   HYPERDX_API_KEY=<INGESTION-PASSWORD>
   ```

5. **Edit secret.env with the connection information to your service**

6. **Edit secret.env with your own HyperDX API key to securely ingest data**

7. **Start all services**
   ```bash
   kubectl apply -k .
   ```

8. **(Optional) Port forward the frontend service**
   ```bash
   kubectl -n clickstack-demo port-forward svc/subscription-app 8000:8000
   ```

9. **(Optional) Access the subscription app in your browser**
    - http://localhost:8000

## Remove resources

```bash
kubectl delete -k .
```

This also removes the namespace, the PVC (and thus the Postgres data), and the
generated Secret. The `clickstack-demo-otel-collector`
ClusterRole/ClusterRoleBinding are cluster-scoped and are removed by
`delete -k` as well.

## Common tweaks

- **More/less load:** edit `LOCUST_USERS` in `load-generator.yaml`.
- **Use a different local port:** change the left-hand side of the
  port-forward, e.g. `port-forward svc/subscription-app 9000:8000`.
- **Rotate credentials:** edit `secret.env`, re-run `kubectl apply -k .`, then
  restart the pods so they pick up the new values (the Secret name is stable, so
  an updated Secret alone won't restart anything):

  ```bash
  kubectl apply -k .
  kubectl -n clickstack-demo rollout restart deployment
  ```
