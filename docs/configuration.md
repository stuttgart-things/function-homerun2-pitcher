# Configuration

## Input schema (`fn.homerun.io/v1alpha1` · `PitchInput`)

Set this on the WatchOperation's `pipeline[].input`:

| Field            | Required | Default    | Notes                                                                  |
|------------------|----------|------------|------------------------------------------------------------------------|
| `endpoint`       | yes      | —          | Base URL of `homerun2-omni-pitcher`; the function POSTs to `/pitch`.   |
| `stream`         | yes      | —          | Logical channel name (forwarded as the Message `system` field).        |
| `payloadMode`    | no       | `envelope` | `envelope` = stable subset; `full` = entire watched resource.          |
| `timeoutSeconds` | no       | `10`       | HTTP timeout in seconds (`>0`, `<=300`).                               |

`extra='forbid'` is set on the schema, so typos like `endPoint` are rejected at validation time.

## Payload shapes

In **envelope** mode (default) the function reduces the watched resource to a stable subset before embedding it in the Message:

```json
{
  "apiVersion": "...", "kind": "...",
  "namespace": "...", "name": "...",
  "uid": "...", "resourceVersion": "...",
  "spec": { ... }, "status": { ... }
}
```

`managedFields`, annotations, and any other keys are dropped. `spec` and `status` are passed through verbatim when present.

In **full** mode the entire watched resource is embedded verbatim.

## Outgoing request body (Message)

`homerun2-omni-pitcher`'s `/pitch` endpoint requires the Message schema. The function constructs:

```json
{
  "title":    "ConfigMap demo/hello",
  "message":  "<JSON-encoded envelope or full payload>",
  "severity": "info",
  "author":   "function-homerun2-pitcher",
  "system":   "<your-stream-name>",
  "tags":     "<Kind>,<namespace>"
}
```

The original payload is preserved as a JSON string in `message`, so downstream consumers can reconstruct it.

## Auth token

The function reads `PITCH_AUTH_TOKEN` from its pod environment and sends it as `Authorization: Bearer <token>`. Mount it from a Secret via `DeploymentRuntimeConfig`:

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

The pod fails fast on startup if `PITCH_AUTH_TOKEN` is missing. Pass `--skip-token-check` only when running locally via `hatch run development`.
