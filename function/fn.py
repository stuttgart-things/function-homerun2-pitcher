"""RunFunction handler for function-homerun2-pitcher.

This is a Crossplane v2 Operation function. It is wired into a
WatchOperation pipeline. On every watched-resource event, Crossplane
injects the resource under the required-resource key
``ops.crossplane.io/watched-resource``. This handler reads it, builds
a payload, and POSTs it to the homerun2-omni-pitcher ``/pitch`` endpoint.
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any

import httpx
import pydantic
from crossplane.function import logging, request, resource, response
from crossplane.function.proto.v1 import run_function_pb2 as fnv1
from crossplane.function.proto.v1 import run_function_pb2_grpc as grpcv1

from function.input.v1alpha1 import PayloadMode, PitchInput

if TYPE_CHECKING:
    import grpc

AUTH_TOKEN_ENV = "PITCH_AUTH_TOKEN"  # noqa: S105
WATCHED_RESOURCE_KEY = "ops.crossplane.io/watched-resource"


AUTHOR = "function-homerun2-pitcher"


def _build_envelope(res: dict[str, Any]) -> dict[str, Any]:
    """Reduce a watched resource to the stable envelope shape.

    The envelope is `{apiVersion, kind, namespace, name, uid,
    resourceVersion, spec, status}` — everything a downstream consumer
    needs to act on a change, without the noise of managed-fields and
    annotations.
    """
    meta = res.get("metadata", {}) or {}
    envelope: dict[str, Any] = {
        "apiVersion": res.get("apiVersion"),
        "kind": res.get("kind"),
        "namespace": meta.get("namespace"),
        "name": meta.get("name"),
        "uid": meta.get("uid"),
        "resourceVersion": meta.get("resourceVersion"),
    }
    if "spec" in res:
        envelope["spec"] = res["spec"]
    if "status" in res:
        envelope["status"] = res["status"]
    return envelope


def _build_message(
    watched: dict[str, Any], payload: dict[str, Any], stream: str
) -> dict[str, Any]:
    """Wrap an envelope/full payload in the pitcher's Message schema.

    homerun2-omni-pitcher's `/pitch` endpoint requires top-level `title`
    and `message` fields (see its README). Map the watched resource into
    those, embedding the full payload as JSON in `message` so downstream
    consumers can still reconstruct it.
    """
    meta = watched.get("metadata", {}) or {}
    kind = watched.get("kind") or "Object"
    name = meta.get("name") or "unknown"
    namespace = meta.get("namespace") or ""
    target = f"{namespace}/{name}" if namespace else name
    tags = ",".join(filter(None, [kind, namespace]))

    return {
        "title": f"{kind} {target}",
        "message": json.dumps(payload, sort_keys=True),
        "severity": "info",
        "author": AUTHOR,
        "system": stream,
        "tags": tags,
    }


class FunctionRunner(grpcv1.FunctionRunnerService):
    """Forward watched-resource events to homerun2-omni-pitcher."""

    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        """Create a new FunctionRunner.

        Args:
            http_client: Optional injected httpx.AsyncClient (for tests).
                When None, the handler creates a per-call client with
                the input's `timeoutSeconds`.
        """
        self.log = logging.get_logger()
        self._http_client = http_client

    async def RunFunction(  # noqa: PLR0911
        self,
        req: fnv1.RunFunctionRequest,
        _: grpc.aio.ServicerContext,
    ) -> fnv1.RunFunctionResponse:
        """Handle a single RunFunctionRequest."""
        log = self.log.bind(tag=req.meta.tag)
        rsp = response.to(req)

        try:
            pi = PitchInput.model_validate(resource.struct_to_dict(req.input))
        except pydantic.ValidationError as e:
            response.fatal(rsp, f"invalid PitchInput: {e.errors()}")
            return rsp

        watched = request.get_watched_resource(req)
        if watched is None:
            response.fatal(
                rsp,
                f"no watched resource found under required-resource key "
                f"{WATCHED_RESOURCE_KEY!r}",
            )
            return rsp

        token = os.environ.get(AUTH_TOKEN_ENV)
        if not token:
            response.fatal(rsp, f"{AUTH_TOKEN_ENV} env var is not set")
            return rsp

        payload = (
            watched if pi.payload_mode == PayloadMode.FULL else _build_envelope(watched)
        )

        meta = watched.get("metadata", {}) or {}
        log = log.bind(
            watched_kind=watched.get("kind"),
            watched_namespace=meta.get("namespace"),
            watched_name=meta.get("name"),
            stream=pi.stream,
            payload_mode=pi.payload_mode.value,
        )

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Pitch-Stream": pi.stream,
        }
        body = _build_message(watched, payload, pi.stream)
        url = pi.pitch_url()

        log.info("Pitching watched resource", url=url)
        try:
            http_response = await self._post(url, body, headers, pi.timeout_seconds)
        except httpx.TimeoutException as e:
            log.error("Pitcher request timed out", error=str(e))
            response.fatal(
                rsp, f"pitcher request timed out after {pi.timeout_seconds}s"
            )
            return rsp
        except httpx.HTTPError as e:
            log.error("Pitcher request failed", error=str(e))
            response.fatal(rsp, f"pitcher request failed: {e}")
            return rsp

        if http_response.status_code < 200 or http_response.status_code >= 300:  # noqa: PLR2004
            log.error(
                "Pitcher returned non-2xx",
                status=http_response.status_code,
                body=http_response.text[:512],
            )
            response.fatal(
                rsp,
                f"pitcher returned {http_response.status_code}: "
                f"{http_response.text[:256]}",
            )
            return rsp

        message_id = ""
        try:
            data = http_response.json()
            if isinstance(data, dict):
                message_id = str(data.get("id") or data.get("message_id") or "")
        except ValueError:
            data = None

        log.info(
            "Pitch accepted",
            status=http_response.status_code,
            message_id=message_id or "<none>",
        )

        if isinstance(data, dict):
            response.set_output(rsp, {"stream": pi.stream, "pitcher": data})

        response.normal(
            rsp,
            f"pitched to stream {pi.stream!r} (id={message_id or 'n/a'})",
        )
        return rsp

    async def _post(
        self,
        url: str,
        body: dict[str, Any],
        headers: dict[str, str],
        timeout: float,  # noqa: ASYNC109
    ) -> httpx.Response:
        """POST to the pitcher. Reuses an injected client if present."""
        if self._http_client is not None:
            return await self._http_client.post(
                url, json=body, headers=headers, timeout=timeout
            )
        async with httpx.AsyncClient(timeout=timeout) as client:
            return await client.post(url, json=body, headers=headers)
