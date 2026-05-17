"""Tests for the RunFunction handler."""

import httpx
import pytest
import respx
from crossplane.function import resource
from crossplane.function.proto.v1 import run_function_pb2 as fnv1

from function.fn import AUTH_TOKEN_ENV, _build_envelope
from tests.conftest import (
    PITCH_URL,
    VALID_INPUT,
    WATCHED_CONFIGMAP,
    build_request,
)

NORMAL = fnv1.SEVERITY_NORMAL
FATAL = fnv1.SEVERITY_FATAL


def _severities(rsp: fnv1.RunFunctionResponse) -> list[int]:
    return [r.severity for r in rsp.results]


def _messages(rsp: fnv1.RunFunctionResponse) -> list[str]:
    return [r.message for r in rsp.results]


async def test_happy_path_envelope_mode(runner):
    """Envelope mode strips noise and posts a Message-shape with the envelope JSON."""
    req = build_request()

    with respx.mock(assert_all_called=True) as r:
        route = r.post(PITCH_URL).mock(
            return_value=httpx.Response(
                200, json={"id": "msg-1", "stream": "configmaps"}
            )
        )
        rsp = await runner.RunFunction(req, None)

    assert _severities(rsp) == [NORMAL]
    assert "msg-1" in _messages(rsp)[0]

    sent = route.calls.last.request
    assert sent.headers["authorization"] == "Bearer test-token-value"
    assert sent.headers["content-type"].startswith("application/json")
    assert sent.headers["x-pitch-stream"] == "configmaps"

    import json

    body = json.loads(sent.content)
    # Pitcher Message schema: title + message are required.
    assert body["title"] == "ConfigMap demo/hello"
    assert body["severity"] == "info"
    assert body["system"] == "configmaps"
    assert body["tags"] == "ConfigMap,demo"
    # The envelope (sans managedFields/data) is embedded as JSON in `message`.
    envelope = json.loads(body["message"])
    assert set(envelope) == {
        "apiVersion",
        "kind",
        "namespace",
        "name",
        "uid",
        "resourceVersion",
    }
    assert "managedFields" not in envelope
    assert "data" not in envelope

    # response.output gets the pitcher reply for downstream consumers.
    out = resource.struct_to_dict(rsp.output)
    assert out["stream"] == "configmaps"
    assert out["pitcher"]["id"] == "msg-1"


async def test_happy_path_full_mode(runner):
    """Full mode forwards the entire watched resource verbatim inside Message.message."""
    pi = {**VALID_INPUT, "payloadMode": "full"}
    req = build_request(pitch_input=pi)

    with respx.mock(assert_all_called=True) as r:
        route = r.post(PITCH_URL).mock(
            return_value=httpx.Response(200, json={"id": "x"})
        )
        rsp = await runner.RunFunction(req, None)

    assert _severities(rsp) == [NORMAL]
    import json

    body = json.loads(route.calls.last.request.content)
    assert body["title"] == "ConfigMap demo/hello"
    assert json.loads(body["message"]) == WATCHED_CONFIGMAP


async def test_full_mode_when_watched_lacks_spec_status(runner):
    """Envelope works for ConfigMap-shaped resources that have no spec/status."""
    req = build_request()
    with respx.mock() as r:
        route = r.post(PITCH_URL).mock(
            return_value=httpx.Response(200, json={"id": "x"})
        )
        await runner.RunFunction(req, None)

    import json

    body = json.loads(route.calls.last.request.content)
    envelope = json.loads(body["message"])
    # spec/status are optional in the envelope and absent here.
    assert "spec" not in envelope
    assert "status" not in envelope


async def test_envelope_with_spec_and_status_xr_shape():
    """Envelope helper passes spec/status through for resources that have them."""
    xr = {
        "apiVersion": "example.crossplane.io/v1",
        "kind": "XR",
        "metadata": {
            "name": "x",
            "namespace": "ns",
            "uid": "u",
            "resourceVersion": "9",
        },
        "spec": {"region": "eu-central-1"},
        "status": {"phase": "Ready"},
    }
    env = _build_envelope(xr)
    assert env["spec"] == {"region": "eu-central-1"}
    assert env["status"] == {"phase": "Ready"}


async def test_pitcher_401_is_fatal(runner):
    req = build_request()
    with respx.mock() as r:
        r.post(PITCH_URL).mock(return_value=httpx.Response(401, text="unauthorized"))
        rsp = await runner.RunFunction(req, None)

    assert _severities(rsp) == [FATAL]
    assert "401" in _messages(rsp)[0]
    assert "unauthorized" in _messages(rsp)[0]


async def test_pitcher_500_is_fatal(runner):
    req = build_request()
    with respx.mock() as r:
        r.post(PITCH_URL).mock(return_value=httpx.Response(503, text="overloaded"))
        rsp = await runner.RunFunction(req, None)

    assert _severities(rsp) == [FATAL]
    assert "503" in _messages(rsp)[0]


async def test_pitcher_timeout_is_fatal(runner):
    req = build_request()
    with respx.mock() as r:
        r.post(PITCH_URL).mock(side_effect=httpx.ConnectTimeout("timed out"))
        rsp = await runner.RunFunction(req, None)

    assert _severities(rsp) == [FATAL]
    assert "timed out" in _messages(rsp)[0].lower()


async def test_generic_http_error_is_fatal(runner):
    req = build_request()
    with respx.mock() as r:
        r.post(PITCH_URL).mock(side_effect=httpx.ConnectError("connection refused"))
        rsp = await runner.RunFunction(req, None)

    assert _severities(rsp) == [FATAL]
    assert "pitcher request failed" in _messages(rsp)[0]


async def test_missing_watched_resource_is_fatal(runner):
    req = build_request(watched=None)
    rsp = await runner.RunFunction(req, None)

    assert _severities(rsp) == [FATAL]
    assert "ops.crossplane.io/watched-resource" in _messages(rsp)[0]


async def test_invalid_input_is_fatal(runner):
    """Empty `stream` violates the schema's min_length=1."""
    bad = {**VALID_INPUT, "stream": ""}
    req = build_request(pitch_input=bad)
    rsp = await runner.RunFunction(req, None)

    assert _severities(rsp) == [FATAL]
    assert "invalid PitchInput" in _messages(rsp)[0]


async def test_missing_endpoint_is_fatal(runner):
    bad = {k: v for k, v in VALID_INPUT.items() if k != "endpoint"}
    req = build_request(pitch_input=bad)
    rsp = await runner.RunFunction(req, None)

    assert _severities(rsp) == [FATAL]
    assert "invalid PitchInput" in _messages(rsp)[0]


async def test_unknown_field_rejected_by_schema(runner):
    """extra='forbid' on the schema catches typos like `endPoint`."""
    bad = {**VALID_INPUT, "endPoint": "http://x"}
    req = build_request(pitch_input=bad)
    rsp = await runner.RunFunction(req, None)

    assert _severities(rsp) == [FATAL]


async def test_missing_token_is_fatal(runner, monkeypatch):
    """Handler-level safety net even though main.py fails fast at startup."""
    monkeypatch.delenv(AUTH_TOKEN_ENV, raising=False)
    req = build_request()
    rsp = await runner.RunFunction(req, None)

    assert _severities(rsp) == [FATAL]
    assert AUTH_TOKEN_ENV in _messages(rsp)[0]


async def test_pitcher_reply_without_id_is_still_accepted(runner):
    """A 2xx with a body that isn't valid JSON shouldn't fail the function."""
    req = build_request()
    with respx.mock() as r:
        r.post(PITCH_URL).mock(return_value=httpx.Response(200, text="ok"))
        rsp = await runner.RunFunction(req, None)

    assert _severities(rsp) == [NORMAL]
    assert "n/a" in _messages(rsp)[0]


async def test_pitcher_url_includes_pitch_path(runner):
    """endpoint with a trailing slash still produces a single /pitch suffix."""
    pi = {**VALID_INPUT, "endpoint": "http://pitcher.svc:8080/"}
    req = build_request(pitch_input=pi)
    with respx.mock() as r:
        route = r.post(PITCH_URL).mock(
            return_value=httpx.Response(200, json={"id": "z"})
        )
        await runner.RunFunction(req, None)
    assert str(route.calls.last.request.url) == PITCH_URL


@pytest.mark.parametrize("api_version", ["fn.homerun.io/v1beta1", "wrong/v1"])
async def test_wrong_api_version_is_fatal(runner, api_version):
    pi = {**VALID_INPUT, "apiVersion": api_version}
    req = build_request(pitch_input=pi)
    rsp = await runner.RunFunction(req, None)
    assert _severities(rsp) == [FATAL]
