# Runbook: backend build & deploy

> **대상 환경:** master-node에서 `docker build` → in-cluster registry push → `kubectl apply -k` 으로 backend Deployment를 띄운다.
> 전제: [insecure-registry runbook](insecure-registry.md) 의 B-1 / B-2 가 완료돼 있어야 한다.

## 1) 이미지 빌드 + 푸시 (master-node)

repo가 master-node에 cloning 돼 있다는 가정. 없으면 `git clone` 부터.

```bash
cd /path/to/weekend-k8s-lab

# 새 코드가 들어갈 때마다 태그를 올린다. v1 은 #4 초기 컷.
docker build -t 192.168.56.105:30500/backend:v1 backend/

docker push 192.168.56.105:30500/backend:v1
# v1: digest: sha256:... size: ...

# 검증: registry catalog 에 backend 가 보여야 함
curl -s http://192.168.56.105:30500/v2/_catalog
# {"repositories":["backend",...]}
```

## 2) cloudflared (deferred to #2)

`k8s/base/cloudflared/` 는 commit 돼 있지만 `k8s/base/kustomization.yaml` 의 `resources:` 목록엔 의도적으로 빠져 있다. #2 (Cloudflare Tunnel) 가 닫힐 때 `cloudflared/` 를 다시 추가하고 `secrets.yaml` 를 채워 적용한다. #4 단독 검증은 cluster-internal `curl` 로만 한다 (§4 [AC3 대체] 참조).

## 3) 클러스터 적용

```bash
kubectl apply -k k8s/base

kubectl rollout status -n weekend-k8s-lab deployment/backend
# deployment "backend" successfully rolled out
```

## 4) AC 검증

### [AC1] `/healthz` 200

```bash
kubectl run curl-test --rm -it --restart=Never \
  -n weekend-k8s-lab --image=curlimages/curl:8.10.1 -- \
  curl -fsS http://backend.weekend-k8s-lab.svc.cluster.local/healthz
# {"status":"ok"}
```

probes:
```bash
kubectl get deploy/backend -n weekend-k8s-lab \
  -o jsonpath='{.spec.template.spec.containers[0].livenessProbe}{"\n"}{.spec.template.spec.containers[0].readinessProbe}{"\n"}'
# liveness initialDelaySeconds=30, readiness initialDelaySeconds=0
```

### [AC2] cluster-internal Service 도달

```bash
kubectl get svc/backend -n weekend-k8s-lab
# backend   ClusterIP   <ip>   <none>   80/TCP
```

### [AC3 / AC4 — cluster-internal 대체 검증]

cloudflared 라우팅과 외부 `https://k8sproject...` curl 은 #2 (Cloudflare Tunnel) 가 닫힐 때까지 deferred. 그 사이 동등 검증은 ClusterIP service 로 직접 친다.

```bash
kubectl run curl-test --rm -it --restart=Never \
  -n weekend-k8s-lab --image=curlimages/curl:8.10.1 -- \
  sh -c 'curl -fsS http://backend.weekend-k8s-lab.svc.cluster.local/api/products'

# JSON array, length 50
# 첫 element 형태:
# {
#   "id": "<uuid>",
#   "name": "Camera Model 001",
#   "price_cents": 51500,
#   "thumbnail": "https://loremflickr.com/400/400/camera?lock=<uuid>"
# }
```

### [AC5] `event_log` 행 증가

```bash
COUNT_BEFORE=$(kubectl exec -n weekend-k8s-lab postgres-0 -- \
  psql -U lab -d weekend -At -c 'SELECT count(*) FROM event_log;')

curl -fsS https://k8sproject.limseongin.com/api/products > /dev/null

COUNT_AFTER=$(kubectl exec -n weekend-k8s-lab postgres-0 -- \
  psql -U lab -d weekend -At -c 'SELECT count(*) FROM event_log;')

echo "before=$COUNT_BEFORE after=$COUNT_AFTER"
# after = before + 1

kubectl exec -n weekend-k8s-lab postgres-0 -- \
  psql -U lab -d weekend -c \
  "SELECT event_type, payload FROM event_log ORDER BY id DESC LIMIT 1;"
# event_type='product_viewed', payload={"variant":"list","count":50}
```

### [AC6] 자격증명은 secretRef로만

```bash
grep -RE 'POSTGRES_(USER|PASSWORD)' k8s/base/backend/
# (출력 없음 — 평문 자격증명 없음 확인)
```

## 트러블슈팅

| 증상 | 원인 | 조치 |
|---|---|---|
| `ImagePullBackOff` on backend pod | registry 미신뢰 또는 push 누락 | `curl http://192.168.56.105:30500/v2/_catalog` 로 push 확인, 노드 containerd hosts.toml 확인 ([insecure-registry runbook](insecure-registry.md) B-2) |
| `CrashLoopBackOff`, 로그에 `connection refused` | postgres pod 미준비 / secret 누락 | `kubectl get pods -n weekend-k8s-lab` → postgres-0 Running 확인, `kubectl get secret postgres-credentials -n weekend-k8s-lab` |
| cloudflared `error="failed to dial"` for `/api/*` | backend Service 미생성 또는 이름 불일치 | `kubectl get svc backend -n weekend-k8s-lab`, ConfigMap의 service URL 확인 |
| cloudflared `error="tunnel credentials file ... does not exist"` | `secrets.yaml` 누락 또는 key 오타 | `kubectl get secret cloudflared-credentials -n weekend-k8s-lab -o yaml`, `credentials.json` key 존재 확인 |
| `/api/products` 가 500 | DB 환경변수 또는 schema 누락 | `kubectl logs deploy/backend -n weekend-k8s-lab`, postgres-seed Job completion 확인 |

## 롤백

```bash
kubectl rollout undo -n weekend-k8s-lab deployment/backend
# 또는 완전 제거
kubectl delete -k k8s/base/backend
```
