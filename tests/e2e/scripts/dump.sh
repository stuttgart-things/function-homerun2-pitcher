#!/usr/bin/env bash
# Dump the e2e cluster state for debugging. Called from up.sh's EXIT
# trap and from `task e2e:dump` after a test failure.

set -u

NS_XP="${E2E_NS_XP:-crossplane-system}"
NS_APP="${E2E_NS_APP:-homerun}"
NS_DEMO="${E2E_NS_DEMO:-demo}"

echo "==> dumping cluster state"
kubectl get nodes -o wide || true
kubectl get pods -A -o wide || true

echo "--- ${NS_APP} describe ---"
kubectl describe pods -n "${NS_APP}" || true
echo "--- omni-pitcher logs ---"
kubectl logs -n "${NS_APP}" -l app=homerun2-omni-pitcher \
  --tail=200 --all-containers || true
echo "--- redis logs ---"
kubectl logs -n "${NS_APP}" -l app=redis \
  --tail=50 --all-containers || true
echo "--- redis stream XLEN/XINFO ---"
kubectl exec -n "${NS_APP}" deploy/redis -- redis-cli XLEN configmaps || true
kubectl exec -n "${NS_APP}" deploy/redis -- redis-cli XINFO STREAM configmaps || true

echo "--- ${NS_XP} describe ---"
kubectl describe pods -n "${NS_XP}" || true
echo "--- function pod logs ---"
kubectl logs -n "${NS_XP}" \
  -l pkg.crossplane.io/function=function-homerun2-pitcher \
  --tail=200 --all-containers || true

echo "--- WatchOperations ---"
kubectl get watchoperations.ops.crossplane.io -A -o wide || true
kubectl describe watchoperations.ops.crossplane.io -A || true
echo "--- Operations ---"
kubectl get operations.ops.crossplane.io -A -o wide || true
kubectl describe operations.ops.crossplane.io -A || true

echo "--- ConfigMaps in ${NS_DEMO} ---"
kubectl get configmaps -n "${NS_DEMO}" -o wide || true

echo "--- recent events ---"
kubectl get events -A --sort-by=.lastTimestamp | tail -100 || true
