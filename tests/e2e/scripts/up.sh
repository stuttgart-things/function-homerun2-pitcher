#!/usr/bin/env bash
# Bring up the e2e environment: kind cluster wired to a local OCI registry,
# Crossplane v2 with --enable-operations, Redis + homerun2-omni-pitcher, the
# locally-built xpkg pushed to the in-cluster registry, then the example
# Function + WatchOperation manifests.
#
# Idempotent-ish: any leftover cluster/registry is scrubbed first.

set -euo pipefail

: "${KIND_CLUSTER:?}"
: "${KIND_REGISTRY_NAME:?}"
: "${KIND_REGISTRY_PORT:?}"
: "${E2E_XPKG_TAG:?}"
: "${E2E_NS_XP:?}"
: "${E2E_NS_APP:?}"
: "${E2E_NS_DEMO:?}"

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
MANIFESTS="${REPO_ROOT}/tests/e2e/manifests"
EXAMPLES="${REPO_ROOT}/examples"
PITCH_TOKEN="${PITCH_AUTH_TOKEN:-e2e-not-a-real-secret}"

# Dump cluster state before exiting so CI logs contain enough to debug.
# Runs from a bash EXIT trap on non-zero exit — placed here so it fires
# BEFORE the outer `task e2e` trap deletes the cluster.
dump_state() {
  local code=$?
  if [ "${code}" -ne 0 ]; then
    echo "==> up.sh failed (exit ${code}) — dumping cluster state" >&2
    kubectl get nodes -o wide || true
    kubectl get pods -A -o wide || true
    kubectl describe pods -n "${E2E_NS_APP}" || true
    echo "--- omni-pitcher logs ---"
    kubectl logs -n "${E2E_NS_APP}" -l app=homerun2-omni-pitcher \
      --tail=200 --all-containers || true
    echo "--- redis logs ---"
    kubectl logs -n "${E2E_NS_APP}" -l app=redis \
      --tail=50 --all-containers || true
    echo "--- crossplane-system describe ---"
    kubectl describe pods -n "${E2E_NS_XP}" || true
    echo "--- function pod logs ---"
    kubectl logs -n "${E2E_NS_XP}" \
      -l pkg.crossplane.io/function=function-homerun2-pitcher \
      --tail=200 --all-containers || true
    echo "--- events ---"
    kubectl get events -A --sort-by=.lastTimestamp | tail -100 || true
  fi
}
trap dump_state EXIT

echo "==> scrub leftover cluster + registry"
kind delete cluster --name "${KIND_CLUSTER}" >/dev/null 2>&1 || true
docker rm -f "${KIND_REGISTRY_NAME}" >/dev/null 2>&1 || true

echo "==> start local registry on :${KIND_REGISTRY_PORT}"
docker run -d --restart=always \
  -p "127.0.0.1:${KIND_REGISTRY_PORT}:5000" \
  --name "${KIND_REGISTRY_NAME}" \
  registry:2 >/dev/null

echo "==> create kind cluster with containerd registry mirror"
cat <<EOF | kind create cluster --name "${KIND_CLUSTER}" --config=-
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
containerdConfigPatches:
  - |-
    [plugins."io.containerd.grpc.v1.cri".registry]
      config_path = "/etc/containerd/certs.d"
EOF

# Tell each kind node to resolve localhost:<port> to the registry container.
# Reference: https://kind.sigs.k8s.io/docs/user/local-registry/
REGISTRY_DIR="/etc/containerd/certs.d/localhost:${KIND_REGISTRY_PORT}"
for node in $(kind get nodes --name "${KIND_CLUSTER}"); do
  docker exec "${node}" mkdir -p "${REGISTRY_DIR}"
  cat <<EOF | docker exec -i "${node}" cp /dev/stdin "${REGISTRY_DIR}/hosts.toml"
[host."http://${KIND_REGISTRY_NAME}:5000"]
EOF
done

# Attach the registry to the kind network so nodes can reach it by name.
if [ "$(docker inspect -f='{{json .NetworkSettings.Networks.kind}}' "${KIND_REGISTRY_NAME}")" = 'null' ]; then
  docker network connect kind "${KIND_REGISTRY_NAME}"
fi

echo "==> install Crossplane v2 with --enable-operations"
kubectl create namespace "${E2E_NS_XP}" --dry-run=client -o yaml | kubectl apply -f -
helm repo add crossplane-stable https://charts.crossplane.io/stable >/dev/null
helm repo update >/dev/null
helm upgrade --install crossplane crossplane-stable/crossplane \
  --namespace "${E2E_NS_XP}" \
  --version 2.2.0 \
  --set "args={--enable-operations}" \
  --wait

echo "==> deploy Redis + homerun2-omni-pitcher"
kubectl create namespace "${E2E_NS_APP}" --dry-run=client -o yaml | kubectl apply -f -
kubectl -n "${E2E_NS_APP}" apply -f "${MANIFESTS}/redis.yaml"
kubectl -n "${E2E_NS_APP}" create secret generic homerun2-omni-pitcher-auth \
  --from-literal=token="${PITCH_TOKEN}" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl -n "${E2E_NS_APP}" apply -f "${MANIFESTS}/omni-pitcher.yaml"
kubectl -n "${E2E_NS_APP}" rollout status deploy/redis --timeout=120s
kubectl -n "${E2E_NS_APP}" rollout status deploy/homerun2-omni-pitcher --timeout=120s

echo "==> build + push xpkg to local registry as ${E2E_XPKG_TAG}"
(cd "${REPO_ROOT}" && task build-xpkg-amd64)
# go-containerregistry (used by `crossplane xpkg push`) auto-detects
# localhost/127.0.0.1 and uses plain HTTP, so no --insecure flag is
# needed — and v2.2.0 doesn't accept one.
crossplane xpkg push \
  --package-files="${REPO_ROOT}/dist/function-homerun2-pitcher-amd64.xpkg" \
  "${E2E_XPKG_TAG}"

echo "==> install Function + runtime config + auth secret"
kubectl -n "${E2E_NS_XP}" create secret generic homerun2-pitcher-auth \
  --from-literal=token="${PITCH_TOKEN}" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f "${EXAMPLES}/runtimeconfig.yaml"

# Patch the example Function to point at our local-registry xpkg instead of
# the released ghcr.io tag.
KIND_REG_INCLUSTER_TAG="${KIND_REGISTRY_NAME}:5000/function-homerun2-pitcher:e2e"
sed "s|ghcr.io/stuttgart-things/function-homerun2-pitcher:v0.1.0|${KIND_REG_INCLUSTER_TAG}|" \
  "${EXAMPLES}/function.yaml" | kubectl apply -f -

echo "==> wait for Function HEALTHY"
kubectl wait function.pkg.crossplane.io/function-homerun2-pitcher \
  --for=condition=Healthy --timeout=180s

echo "==> apply WatchOperation"
kubectl create namespace "${E2E_NS_DEMO}" --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f "${EXAMPLES}/watchoperation.yaml"

echo "==> e2e:up done"
