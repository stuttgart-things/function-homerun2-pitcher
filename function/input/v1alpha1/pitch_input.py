"""PitchInput schema (fn.homerun.io/v1alpha1).

WatchOperation authors set this via `pipeline[].input`. Example:

    apiVersion: fn.homerun.io/v1alpha1
    kind: PitchInput
    endpoint: http://homerun2-omni-pitcher.homerun.svc:8080
    stream: claims
    payloadMode: envelope
    timeoutSeconds: 10
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

API_VERSION = "fn.homerun.io/v1alpha1"
KIND = "PitchInput"


class PayloadMode(str, Enum):
    """Shape of the payload sent to the pitcher /pitch endpoint."""

    FULL = "full"
    ENVELOPE = "envelope"


class PitchInput(BaseModel):
    """Input for the homerun2-pitcher Operation function.

    Attributes:
        api_version: Must equal ``fn.homerun.io/v1alpha1``.
        kind: Must equal ``PitchInput``.
        endpoint: Base URL of the homerun2-omni-pitcher service. The
            function POSTs to ``<endpoint>/pitch``.
        stream: Redis stream name forwarded to the pitcher; usually
            corresponds to a logical channel like ``claims``.
        payload_mode: Whether to forward the entire watched resource
            (``full``) or only a stable envelope (``envelope``).
        timeout_seconds: HTTP request timeout when calling the pitcher.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    api_version: str = Field(default=API_VERSION, alias="apiVersion")
    kind: str = Field(default=KIND)
    endpoint: HttpUrl
    stream: str = Field(min_length=1)
    payload_mode: PayloadMode = Field(default=PayloadMode.ENVELOPE, alias="payloadMode")
    timeout_seconds: float = Field(default=10.0, gt=0, le=300, alias="timeoutSeconds")

    @field_validator("api_version")
    @classmethod
    def _check_api_version(cls, v: str) -> str:
        if v != API_VERSION:
            msg = f"apiVersion must be {API_VERSION!r}, got {v!r}"
            raise ValueError(msg)
        return v

    @field_validator("kind")
    @classmethod
    def _check_kind(cls, v: str) -> str:
        if v != KIND:
            msg = f"kind must be {KIND!r}, got {v!r}"
            raise ValueError(msg)
        return v

    def pitch_url(self) -> str:
        """Return the full URL of the /pitch endpoint."""
        base = str(self.endpoint).rstrip("/")
        return f"{base}/pitch"
