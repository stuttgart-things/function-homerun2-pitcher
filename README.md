# function-homerun2-pitcher

A Crossplane **v2 Operation function** (Python) that pitches every
watched-resource event to the
[homerun2-omni-pitcher](https://github.com/stuttgart-things/homerun2-omni-pitcher)
`/pitch` endpoint. The pitcher then writes the payload to a Redis
stream for downstream consumers.

```
+------------------+    inject     +-------------------------+    POST /pitch
| WatchOperation   | ------------> | function-homerun2-pitch | --------------> homerun2-omni-pitcher --> Redis Streams
| (watches K8s     |               | (this function)         |
|  resources)      |               +-------------------------+
+------------------+
```

## Requirements

- Crossplane **v2.x** installed with `--enable-operations`
  (Operations is the API group that ships `WatchOperation`).
- A reachable `homerun2-omni-pitcher` service.
- A Bearer token shared between this function and the pitcher.

## Install

Apply the Function manifest (see [`examples/function.yaml`](examples/function.yaml)):

```yaml
apiVersion: pkg.crossplane.io/v1
kind: Function
metadata:
  name: function-homerun2-pitcher
spec:
  package: ghcr.io/stuttgart-things/function-homerun2-pitcher:v0.1.0
  runtimeConfigRef:
    apiVersion: pkg.crossplane.io/v1beta1
    kind: DeploymentRuntimeConfig
    name: function-homerun2-pitcher
```

The package declares `spec.capabilities: [operation]`, so Crossplane
will accept it in `WatchOperation` pipeline steps.

## Configure

### Input schema (`fn.homerun.io/v1alpha1` · `PitchInput`)

Set this on the WatchOperation's `pipeline[].input`:

| Field            | Required | Default      | Notes                                                                  |
| ---------------- | -------- | ------------ | ---------------------------------------------------------------------- |
| `endpoint`       | yes      | —            | Base URL of `homerun2-omni-pitcher`; the function POSTs to `/pitch`.   |
| `stream`         | yes      | —            | Redis stream name forwarded to the pitcher.                            |
| `payloadMode`    | no       | `envelope`   | `full` = entire watched resource; `envelope` = stable subset (below).  |
| `timeoutSeconds` | no       | `10`         | HTTP timeout (`>0`, `<=300`).                                          |

Envelope shape:

```json
{
  "apiVersion": "...", "kind": "...",
  "namespace": "...", "name": "...",
  "uid": "...", "resourceVersion": "...",
  "spec": { ... }, "status": { ... }
}
```

### Auth token

The function reads `PITCH_AUTH_TOKEN` from its pod environment and
sends it as `Authorization: Bearer <token>`. Mount it from a
`Secret` via `DeploymentRuntimeConfig`:

```yaml
# secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: homerun2-pitcher-auth
  namespace: crossplane-system
stringData:
  token: <bearer token shared with the pitcher>
```

```yaml
# runtimeconfig.yaml — wires the secret into the function pod
apiVersion: pkg.crossplane.io/v1beta1
kind: DeploymentRuntimeConfig
metadata:
  name: function-homerun2-pitcher
spec:
  deploymentTemplate:
    spec:
      selector: {}
      template:
        spec:
          containers:
            - name: package-runtime
              env:
                - name: PITCH_AUTH_TOKEN
                  valueFrom:
                    secretKeyRef:
                      name: homerun2-pitcher-auth
                      key: token
```

The pod fails fast on startup if `PITCH_AUTH_TOKEN` is missing — pass
`--skip-token-check` only when running locally (`hatch run development`).

## Example

A runnable end-to-end demo (watch ConfigMaps in `demo` → pitch each
change → land messages in Redis) lives in
[`examples/`](examples/README.md).

## Develop

```sh
hatch env create
hatch run development              # gRPC server on :9443 (insecure, debug)
hatch run test                     # pytest
task build                         # both amd64 + arm64 xpkgs into dist/
```

A quick render check against the example WatchOperation:

```sh
crossplane render \
  examples/watchoperation.yaml \
  examples/function.yaml \
  <(echo "{}")
```

## Troubleshooting

| Symptom                                                                     | Likely cause                                                                                       |
| --------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| `FATAL: PITCH_AUTH_TOKEN env var is required` in function pod logs           | Secret/runtimeconfig not applied before the Function. Apply them, then `kubectl rollout restart`. |
| Result `pitcher returned 401: …`                                            | Token in the Secret doesn't match `AUTH_TOKEN` on the pitcher.                                     |
| Result `no watched resource found under required-resource key …`            | Crossplane is not running with `--enable-operations`, or the Function lacks `operation` capability.|
| Result `pitcher request timed out after Ns`                                 | Pitcher unreachable or slow; raise `timeoutSeconds` or check service.                              |
| Function pod healthy but no pitches arrive                                  | Confirm WatchOperation is selecting the resource: `kubectl describe watchoperation <name>`.        |

## Related

- [homerun2-omni-pitcher](https://github.com/stuttgart-things/homerun2-omni-pitcher) — the receiving service.
- [Crossplane Operations](https://docs.crossplane.io/) — `WatchOperation`, `CronOperation`, `Operation`.
- [function-template-python](https://github.com/crossplane/function-template-python) — upstream scaffold.

## License

Apache-2.0 — see [`LICENSE`](LICENSE).
