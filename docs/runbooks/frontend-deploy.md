# Runbook: frontend deploy (#6)

> 전제: #4 + #5 통과 (backend:v2 + mongo seed 완료). 빌드/푸시 일반 절차는 [backend-build-and-deploy.md](backend-build-and-deploy.md) §1 와 동일 패턴.

## 1) 빌드 + 푸시 (master-node)

```bash
cd /path/to/weekend-k8s-lab
git fetch origin feat/6-frontend
git checkout feat/6-frontend

# Multi-stage: node:20-alpine 가 npm install + vite build → nginx:alpine 가 dist/ 만 들고 간다.
docker build -t 192.168.56.105:30500/frontend:v1 frontend/
docker push 192.168.56.105:30500/frontend:v1

curl -s http://192.168.56.105:30500/v2/_catalog
# {"repositories":["backend","frontend",...]}
```

## 2) apply + rollout

```bash
kubectl apply -k k8s/base
kubectl rollout status -n weekend-k8s-lab deployment/frontend --timeout=120s
kubectl get pods -n weekend-k8s-lab -l app=frontend -o wide
```

## 3) AC 검증 (cluster-internal — 외부 URL ACs 는 #2 까지 deferred)

```bash
kubectl -n weekend-k8s-lab port-forward svc/frontend 18081:80 >/tmp/pf-fe.log 2>&1 &
PF=$!
trap "kill $PF 2>/dev/null || true" EXIT
sleep 2
```

### [AC1] 이미지 빌드 + push 성공
위 §1 확인.

### [AC2] nginx SPA fallback 동작

```bash
# 루트 — index.html 직접 서빙
curl -fsS http://127.0.0.1:18081/ | head -20
# <!doctype html> ... <div id="root"></div> ... /src/main.tsx (dev) 또는 /assets/index-*.js (prod build)

# 존재하지 않는 client-side route — SPA fallback 으로 index.html 동일 응답
curl -fsSI http://127.0.0.1:18081/products/some-fake-id | head -3
# HTTP/1.1 200 OK
# Content-Type: text/html

curl -fsS http://127.0.0.1:18081/products/some-fake-id | grep -q '<div id="root">' && echo "SPA fallback OK"

# 빌드된 asset 경로
ASSET=$(curl -fsS http://127.0.0.1:18081/ | grep -oE '/assets/index-[A-Za-z0-9_-]+\.js' | head -1)
echo "asset=$ASSET"
curl -fsSI http://127.0.0.1:18081$ASSET | head -3
# HTTP/1.1 200 OK
# Content-Type: application/javascript
# Cache-Control: public, immutable (from nginx.conf)
```

### [AC3] cloudflared 라우팅 (deferred to #2)

ConfigMap 의 route 는 `/` → frontend, `/api/*` → backend 로 이미 작성됨. cloudflared Deployment 자체는 #2 에서 띄움.

### [AC4 / AC5 / AC6 — 브라우저 검증 (deferred to #2)]

50개 카드 그리드, 클릭 navigate, deep-link refresh 는 실제 브라우저가 있어야 검증. #2 (Cloudflare Tunnel) 닫히면 `https://k8sproject.limseongin.com` 로 다음을 확인:

- 루트 → 50개 카메라 그리드
- 카드 클릭 → `/products/<uuid>` 로 navigate + detail (description + specs + reviews) 표시
- detail 페이지에서 새로고침 → 동일 페이지 다시 로드 (nginx fallback 으로 200 응답)

대체 검증: master-node 에서 `curl -fsS http://127.0.0.1:18081/api/products` 가 작동하는지 (backend Service 도 같은 cluster 내). 단, 이 port-forward 는 frontend 만 향하므로 `/api/*` 는 안 됨. backend port-forward 따로:
```bash
kubectl -n weekend-k8s-lab port-forward svc/backend 18080:80 &
curl -fsS http://127.0.0.1:18080/api/products | python3 -c 'import json,sys;print(len(json.load(sys.stdin)),"products")'
# 50 products
```

## 트러블슈팅

| 증상 | 원인 | 조치 |
|---|---|---|
| frontend Pod `CrashLoopBackOff`, log `nginx: [emerg] ... directive ... in /etc/nginx/conf.d/default.conf` | nginx.conf 문법 오류 | nginx.conf 수정 후 backend:v2 와 같은 패턴으로 v2 빌드/push, 재배포 |
| `curl /` returns 404 | dist/ 가 비어서 nginx가 정적 파일 못 찾음 | `docker build` 단계의 vite build 출력 확인, `dist/index.html` 존재 여부 |
| `curl /assets/...js` returns 404 | hashed asset 이름이 매 빌드마다 달라짐 | `curl /` 의 HTML 에서 현재 asset path 다시 추출 |
| `npm install` 단계에서 peer dep 오류 | react 19 + 호환 안 되는 lib | `frontend/package.json` 의 dep 버전 핀 확인 |
| 브라우저에서 `/products/:id` 새로고침 시 404 | nginx try_files fallback 누락 | `frontend/nginx.conf` 의 `location /` 블록에 `try_files $uri $uri/ /index.html;` 확인 |
