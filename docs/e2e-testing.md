# End-to-End Testing

The repo ships a complete end-to-end test that brings up kind, installs Crossplane v2 with `--enable-operations`, deploys Redis Stack + omni-pitcher, builds the xpkg from the local source, applies the example Function + WatchOperation, creates a ConfigMap, and asserts a new entry lands in the Redis stream.

## Running locally

Prerequisites: `kind`, `kubectl`, `helm`, `task`, `crossplane` CLI, `hatch`, `docker`.

```sh
task e2e
```

That single command runs `e2e:up` → `e2e:test` → unconditional `e2e:dump` → `e2e:down`. The dump runs even on success and is cheap; on failure it surfaces the pod state and logs you need to debug.

Individual phases:

| Task          | What it does                                                                                                |
|---------------|-------------------------------------------------------------------------------------------------------------|
| `e2e:up`      | kind + local registry + Crossplane v2.2.0 + Redis Stack + omni-pitcher + Function + WatchOperation         |
| `e2e:test`    | pytest assertion: `XLEN <stream>` grows after a ConfigMap event                                             |
| `e2e:dump`    | pods, logs, Operations, WatchOperations, events, Redis stream contents                                      |
| `e2e:down`    | kind cluster + registry container teardown                                                                  |

## How the cluster is wired

The standard kind+local-registry pattern has a few wrinkles for Crossplane v2:

1. **Registry address requires a dot.** Crossplane v2's `spec.package` validator rejects hostnames without a dot (so `localhost:5001` and `kind-registry:5000` both fail). The script uses the registry container's IP on the `kind` docker bridge (`172.18.0.x:5000`).
2. **Crossplane fetches over HTTP, not via containerd.** The containerd registry mirror only redirects kubelet image pulls. The package manager pod's Go HTTP client doesn't know about `/etc/containerd/certs.d`, so the package URL has to be routable from inside the cluster (the bridge IP is).
3. **Containerd certs.d entry for kubelet.** The kind nodes still need a certs.d entry under `${IP}:5000` so kubelet's runtime image pull uses plain HTTP.
4. **Redis Stack, not vanilla Redis.** The pitcher stores each Message as a RedisJSON document (`JSON.SET`), which is only available in Redis Stack.

## CI

The `CI - E2E` workflow runs on every PR + push to main + `workflow_dispatch`. It pins to a self-hosted `kind-testing-runner-*` runner. The workflow only handles tool install + cluster scrub/cleanup + diagnostics; all real work lives in `task e2e`.

## Files

| Path                                          | Purpose                                                       |
|-----------------------------------------------|---------------------------------------------------------------|
| `.github/workflows/e2e.yaml`                  | The CI workflow                                              |
| `Taskfile.yaml`                               | `e2e`, `e2e:up`, `e2e:test`, `e2e:dump`, `e2e:down` tasks    |
| `tests/e2e/scripts/up.sh`                     | Cluster + Crossplane + xpkg push + Function install         |
| `tests/e2e/scripts/dump.sh`                   | Diagnostics dump (called by the task wrapper + EXIT trap)   |
| `tests/e2e/manifests/redis.yaml`              | Redis Stack Deployment/Service                              |
| `tests/e2e/manifests/omni-pitcher.yaml`       | omni-pitcher v1.11.x Deployment/Service                     |
| `tests/e2e/manifests/watchoperation.yaml`     | Stripped WatchOperation fixture (no `operationTemplate.metadata`) |
| `tests/e2e/test_pitch.py`                     | pytest assertion (`@pytest.mark.e2e`)                       |

## Filtering pytest

The `e2e` marker is registered in `pyproject.toml`. `hatch run test` deselects e2e tests so unit runs don't try to connect to a cluster. To run only e2e:

```sh
hatch run test-e2e
```
