# function-homerun2-pitcher

A Crossplane **v2 Operation function** (Python) that pitches every watched-resource event to the [homerun2-omni-pitcher](https://github.com/stuttgart-things/homerun2-omni-pitcher) `/pitch` endpoint. The pitcher then writes the payload to a Redis stream for downstream consumers.

## Overview

```
+----------------+   inject    +-----------------------------+   POST /pitch
| WatchOperation | ----------> | function-homerun2-pitcher   | --------------> homerun2-omni-pitcher --> Redis Streams
| (K8s watcher)  |             | (this function)             |
+----------------+             +-----------------------------+
```

Every change to a watched resource (e.g. `ConfigMap`) triggers an Operation pipeline. This function sits in that pipeline, reads the injected resource, builds a Message-shaped payload, and forwards it to the pitcher. The pitcher enqueues the message into a Redis Stack stream (`JSON.SET` + `XADD`) for consumers like [homerun2-core-catcher](https://github.com/stuttgart-things/homerun2-core-catcher).

## Requirements

- Crossplane **v2.x** installed with `--enable-operations` (the API group that ships `WatchOperation`).
- A reachable `homerun2-omni-pitcher` service.
- A Bearer token shared between this function and the pitcher.
- Redis Stack (or any Redis with the RedisJSON module) backing the pitcher.

## Install

```yaml
apiVersion: pkg.crossplane.io/v1
kind: Function
metadata:
  name: function-homerun2-pitcher
spec:
  package: ghcr.io/stuttgart-things/function-homerun2-pitcher:v1.0.1
  runtimeConfigRef:
    apiVersion: pkg.crossplane.io/v1beta1
    kind: DeploymentRuntimeConfig
    name: function-homerun2-pitcher
```

The package declares `spec.capabilities: [operation]`, so Crossplane accepts it in `WatchOperation` pipeline steps.

## Architecture

- **Python 3.12+** — gRPC server built on `crossplane-function-sdk-python`.
- **httpx** — async HTTP client for the pitcher call.
- **Pydantic** — strict input schema (`fn.homerun.io/v1alpha1` · `PitchInput`).
- **xpkg** — multi-arch (amd64 + arm64), built with `crossplane xpkg build`, embedding a distroless runtime image.

## Related

- [homerun2-omni-pitcher](https://github.com/stuttgart-things/homerun2-omni-pitcher) — the receiving service.
- [homerun2-core-catcher](https://github.com/stuttgart-things/homerun2-core-catcher) — example downstream consumer.
- [Crossplane Operations](https://docs.crossplane.io/) — `WatchOperation`, `CronOperation`, `Operation`.
- [function-template-python](https://github.com/crossplane/function-template-python) — upstream scaffold.
