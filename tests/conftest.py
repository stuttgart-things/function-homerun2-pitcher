"""Shared pytest fixtures."""

import os

import httpx
import pytest
import pytest_asyncio
from crossplane.function import logging, resource
from crossplane.function.proto.v1 import run_function_pb2 as fnv1

from function.fn import AUTH_TOKEN_ENV, WATCHED_RESOURCE_KEY, FunctionRunner

logging.configure(level=logging.Level.DISABLED)


VALID_INPUT = {
    "apiVersion": "fn.homerun.io/v1alpha1",
    "kind": "PitchInput",
    "endpoint": "http://pitcher.svc:8080",
    "stream": "configmaps",
    "payloadMode": "envelope",
    "timeoutSeconds": 5,
}

WATCHED_CONFIGMAP = {
    "apiVersion": "v1",
    "kind": "ConfigMap",
    "metadata": {
        "name": "hello",
        "namespace": "demo",
        "uid": "u-1234",
        "resourceVersion": "42",
        "managedFields": [{"manager": "kubectl", "noise": "yes"}],
    },
    "data": {"greeting": "hi"},
}


PITCH_URL = "http://pitcher.svc:8080/pitch"


def build_request(
    pitch_input: dict | None = VALID_INPUT,
    watched: dict | None = WATCHED_CONFIGMAP,
) -> fnv1.RunFunctionRequest:
    """Build a RunFunctionRequest with optional input and watched resource."""
    req = fnv1.RunFunctionRequest(meta=fnv1.RequestMeta(tag="test"))
    if pitch_input is not None:
        req.input.CopyFrom(resource.dict_to_struct(pitch_input))
    if watched is not None:
        items = req.required_resources[WATCHED_RESOURCE_KEY].items
        items.add().resource.CopyFrom(resource.dict_to_struct(watched))
    return req


@pytest.fixture(autouse=True)
def _auth_token(monkeypatch):
    """Default every test to having a token set; override per-test as needed."""
    monkeypatch.setenv(AUTH_TOKEN_ENV, "test-token-value")


@pytest_asyncio.fixture
async def runner():
    """A FunctionRunner sharing one httpx.AsyncClient so respx can intercept."""
    async with httpx.AsyncClient() as client:
        yield FunctionRunner(http_client=client)
