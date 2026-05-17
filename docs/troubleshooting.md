# Troubleshooting

## Common errors

| Symptom                                                                     | Likely cause                                                                                       |
|-----------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------|
| `FATAL: PITCH_AUTH_TOKEN env var is required` in function pod logs           | Secret/runtimeconfig not applied before the Function. Apply them, then `kubectl rollout restart deploy/function-homerun2-pitcher -n crossplane-system`. |
| Result `pitcher returned 401: …`                                            | Token in the Secret doesn't match `AUTH_TOKEN` on the pitcher.                                     |
| Result `pitcher returned 400: …"Title is required"`                         | Pitcher is on v1.11.x or later and rejects non-Message bodies. Upgrade the function to a release that sends the Message-shape body (≥ v1.0.1). |
| Result `no watched resource found under required-resource key …`            | Crossplane is not running with `--enable-operations`, or the Function lacks `operation` capability. |
| Result `pitcher request timed out after Ns`                                 | Pitcher unreachable or slow; raise `timeoutSeconds` or check Service.                              |
| Pitcher logs `ERR unknown command 'JSON.SET'`                               | Backing Redis lacks the RedisJSON module. Switch to Redis Stack (`redis/redis-stack-server`).      |
| Function pod healthy but no pitches arrive                                  | Confirm the WatchOperation is selecting the resource: `kubectl describe watchoperation <name>`.    |
| `spec.package: Invalid value: "string": must be a fully qualified image name` | Crossplane v2 rejects hostnames without a dot. Use an FQDN or IP (e.g. `172.18.0.3:5000/...`) for the package reference. |
| `WatchOperation … cannot be handled … unknown field "spec.operationTemplate.metadata.labels"` | Crossplane v2.2.0's strict decoder rejects that subfield. Remove the `metadata` block under `operationTemplate`. |

## Inspecting the pipeline

```sh
# Is the Function healthy?
kubectl get function function-homerun2-pitcher -o yaml | grep -A5 conditions:

# Is the WatchOperation watching?
kubectl describe watchoperation pitch-configmaps

# Operations created per event:
kubectl get operations -A
kubectl describe operation <name>

# Function pod logs (structured JSON):
kubectl -n crossplane-system logs \
  -l pkg.crossplane.io/function=function-homerun2-pitcher --tail=200

# Pitcher logs:
kubectl -n homerun logs deploy/homerun2-omni-pitcher | tail

# Redis stream:
kubectl -n homerun exec deploy/redis -- redis-cli XLEN <stream>
kubectl -n homerun exec deploy/redis -- redis-cli XREVRANGE <stream> + - COUNT 5
```

## Useful function log fields

The function uses [`structlog`](https://www.structlog.org/) bound with:

- `tag` — the `RunFunctionRequest.meta.tag` (lets you correlate with the controller log)
- `watched_kind`, `watched_namespace`, `watched_name` — the resource the WatchOperation injected
- `stream` — the `PitchInput.stream` value
- `payload_mode` — `envelope` or `full`
- `url`, `status` — outgoing request to the pitcher

A successful pitch:

```json
{"msg": "Pitch accepted", "status": 200, "message_id": "..."}
```

A rejected pitch (fatal result on the Operation):

```json
{"msg": "Pitcher returned non-2xx", "status": 400, "body": "{...}"}
```
