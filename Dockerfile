# syntax=docker/dockerfile:1

# Debian 12 base matches the distroless python3-debian12 runtime image.
FROM --platform=$BUILDPLATFORM debian:12-slim AS build

RUN --mount=type=cache,target=/var/lib/apt/lists \
    --mount=type=cache,target=/var/cache/apt \
    rm -f /etc/apt/apt.conf.d/docker-clean \
    && apt-get update \
    && apt-get install --no-install-recommends --yes python3-venv git

ENV PYTHONDONTWRITEBYTECODE=true

WORKDIR /build
RUN --mount=target=. \
    --mount=type=cache,target=/root/.cache/pip \
    python3 -m venv /venv/build \
    && /venv/build/bin/pip install hatch \
    && /venv/build/bin/hatch build -t wheel /whl

RUN --mount=type=cache,target=/root/.cache/pip \
    python3 -m venv /venv/fn \
    && /venv/fn/bin/pip install /whl/*.whl

FROM gcr.io/distroless/python3-debian12 AS image
WORKDIR /
COPY --from=build /venv/fn /venv/fn
EXPOSE 9443
USER nonroot:nonroot
ENTRYPOINT ["/venv/fn/bin/function"]
