# Usage

A complete runnable example lives in [`examples/`](https://github.com/stuttgart-things/function-homerun2-pitcher/tree/main/examples). This page walks through the same flow.

## End-to-end demo

The demo watches `ConfigMap`s in the `demo` namespace and forwards each change to a `homerun2-omni-pitcher` instance, which writes a message to a Redis stream.

### Prerequisites

- Kubernetes cluster (kind works) with **Crossplane v2.x** and `--enable-operations`.
- `homerun2-omni-pitcher` reachable in-cluster at `http://homerun2-omni-pitcher.homerun.svc:8080`, configured with `AUTH_TOKEN`, `REDIS_ADDR`, `REDIS_PORT`, `REDIS_STREAM`.
- Redis Stack (the pitcher uses `JSON.SET`, which the RedisJSON module provides).

### Apply order

1. **Secret** — same token the pitcher was started with:

    ```sh
    kubectl -n crossplane-system apply -f secret.yaml
    ```

2. **Runtime config** — wires the secret into the function pod:

    ```sh
    kubectl apply -f runtimeconfig.yaml
    ```

3. **Function** — pulls the xpkg from ghcr:

    ```sh
    kubectl apply -f function.yaml
    kubectl get function function-homerun2-pitcher -w   # wait for HEALTHY=True
    ```

4. **WatchOperation** — watches `demo` namespace ConfigMaps:

    ```sh
    kubectl create namespace demo
    kubectl apply -f watchoperation.yaml
    ```

## WatchOperation reference

```yaml
apiVersion: ops.crossplane.io/v1alpha1
kind: WatchOperation
metadata:
  name: pitch-configmaps
spec:
  watch:
    apiVersion: v1
    kind: ConfigMap
    namespace: demo
  operationTemplate:
    spec:
      mode: Pipeline
      pipeline:
        - step: pitch
          functionRef:
            name: function-homerun2-pitcher
          input:
            apiVersion: fn.homerun.io/v1alpha1
            kind: PitchInput
            endpoint: http://homerun2-omni-pitcher.homerun.svc:8080
            stream: configmaps
            payloadMode: envelope
            timeoutSeconds: 10
```

!!! warning
    The published `examples/watchoperation.yaml` includes a `metadata.labels` block under `operationTemplate`. Crossplane v2.2.0's strict decoder rejects that subfield as unknown — drop the `metadata` block when applying. See `tests/e2e/manifests/watchoperation.yaml` for the stripped form used in CI.

## Trigger a pitch

```sh
kubectl -n demo create configmap hello --from-literal=greeting=hi
kubectl -n demo annotate configmap hello bumped="$(date +%s)" --overwrite
```

## Verify

```sh
# Pitcher should log POST /pitch with 200
kubectl -n homerun logs deploy/homerun2-omni-pitcher | tail

# Stream should grow
kubectl -n homerun exec deploy/redis -- redis-cli XLEN <your-stream>
kubectl -n homerun exec deploy/redis -- redis-cli XREVRANGE <your-stream> + - COUNT 5
```

Each stream entry is an `XADD` containing the Message's `objectId` (a RedisJSON document under that key holds the full message).

## Local development

```sh
hatch env create
hatch run development              # gRPC server on :9443 (insecure, debug)
hatch run test                     # unit tests (e2e marker deselected)
task build                         # multi-arch xpkgs into dist/
```

Quick render check against the example WatchOperation:

```sh
crossplane render \
  examples/watchoperation.yaml \
  examples/function.yaml \
  <(echo "{}")
```
