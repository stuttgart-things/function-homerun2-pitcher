# Example: pitching ConfigMap changes

End-to-end demo that watches ConfigMaps in the `demo` namespace and
forwards each change to a `homerun2-omni-pitcher` instance, which in
turn writes a message to a Redis stream.

## Prerequisites

- A Kubernetes cluster (kind works) with **Crossplane v2.x** installed
  and started with `--enable-operations`.
- `homerun2-omni-pitcher` reachable in-cluster at
  `http://homerun2-omni-pitcher.homerun.svc:8080` with its
  `AUTH_TOKEN` set to a known value.
- Redis reachable from the pitcher.

## Apply order

1. Replace the placeholder token in `secret.yaml` with the same value
   the pitcher was started with, then apply the secret. The function
   reads it via the env var `PITCH_AUTH_TOKEN`.

   ```sh
   kubectl -n crossplane-system apply -f secret.yaml
   ```

2. Apply the runtime config — this wires the secret into the function
   pod as `PITCH_AUTH_TOKEN`:

   ```sh
   kubectl apply -f runtimeconfig.yaml
   ```

3. Install the Function itself:

   ```sh
   kubectl apply -f function.yaml
   kubectl get function function-homerun2-pitcher -w   # wait for HEALTHY=True
   ```

4. Create the `demo` namespace and the WatchOperation:

   ```sh
   kubectl create namespace demo
   kubectl apply -f watchoperation.yaml
   ```

## Trigger a pitch

```sh
kubectl -n demo create configmap hello --from-literal=greeting=hi
kubectl -n demo annotate configmap hello bumped="$(date +%s)" --overwrite
```

## Verify

- Pitcher logs should show two `POST /pitch` requests:

  ```sh
  kubectl -n homerun logs deploy/homerun2-omni-pitcher | tail
  ```

- Each request should produce a new entry in the `configmaps` Redis
  stream:

  ```sh
  kubectl -n homerun exec deploy/redis -- redis-cli XLEN configmaps
  kubectl -n homerun exec deploy/redis -- redis-cli XREVRANGE configmaps + - COUNT 5
  ```

## Common pitfalls

- **`PITCH_AUTH_TOKEN env var is not set`** — the runtimeconfig didn't
  apply before the Function did. Roll the function pod after fixing
  the secret/runtimeconfig: `kubectl -n crossplane-system rollout
  restart deploy/function-homerun2-pitcher`.
- **`pitcher returned 401`** — the secret value doesn't match the
  pitcher's `AUTH_TOKEN`.
- **`no watched resource found`** — the WatchOperation didn't inject
  the resource. Confirm Crossplane was started with
  `--enable-operations`, and that the Function reports
  `capabilities: [operation]` (`kubectl get function ... -o yaml`).
