"""End-to-end assertion: a ConfigMap change in the `demo` namespace lands
as a new entry in the `configmaps` Redis stream via the
WatchOperation → function → omni-pitcher → Redis path.

Driven by `task e2e:test`. The cluster is brought up by `task e2e:up`
(see tests/e2e/scripts/up.sh) — this module assumes Redis, the pitcher,
Crossplane, the Function and the WatchOperation are already in place.
"""

import os
import subprocess
import time

import pytest

NS_APP = os.environ.get("E2E_NS_APP", "homerun")
NS_DEMO = os.environ.get("E2E_NS_DEMO", "demo")
STREAM = "configmaps"
TIMEOUT_S = 60
POLL_S = 2


def _kubectl(*args: str) -> str:
    out = subprocess.run(
        ["kubectl", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return out.stdout.strip()


def _xlen() -> int:
    raw = _kubectl(
        "-n", NS_APP, "exec", "deploy/redis", "--",
        "redis-cli", "XLEN", STREAM,
    )
    # `redis-cli XLEN` prints just the integer
    return int(raw.splitlines()[-1])


@pytest.mark.e2e
def test_configmap_change_appears_in_redis_stream() -> None:
    # XLEN may not exist yet — XLEN on a missing stream returns 0.
    before = _xlen()

    name = f"e2e-{int(time.time())}"
    _kubectl(
        "-n", NS_DEMO, "create", "configmap", name,
        "--from-literal=greeting=hi",
    )

    deadline = time.monotonic() + TIMEOUT_S
    last = before
    while time.monotonic() < deadline:
        last = _xlen()
        if last > before:
            return
        time.sleep(POLL_S)

    pytest.fail(
        f"redis stream '{STREAM}' did not grow after ConfigMap create: "
        f"before={before} after={last}",
    )
