# Runbook: mongo + backend v2 deploy (#5)

> 전제: #4 통과 (backend:v1 띄워져 있음, postgres-seed 완료). #5 는 mongo StatefulSet 을 worker-node2에 postgres와 co-locate, backend 를 v2로 bump 한다.

빌드/푸시 일반 절차는 [backend-build-and-deploy.md](backend-build-and-deploy.md) §1 와 동일. 여기선 #5 특이사항만.

## 1) 빌드 + 푸시 (master-node)

backend 가 `pymongo` 추가 + `/api/products/{id}` + `app.seed_mongo` 모듈을 포함하므로 새 tag `v2`.

```bash
cd /path/to/weekend-k8s-lab
git fetch origin feat/5-mongo
git checkout feat/5-mongo

docker build -t 192.168.56.105:30500/backend:v2 backend/
docker push 192.168.56.105:30500/backend:v2

curl -s http://192.168.56.105:30500/v2/backend/tags/list
# {"name":"backend","tags":["v1","v2"]}
```

## 2) apply

```bash
kubectl apply -k k8s/base

kubectl rollout status -n weekend-k8s-lab statefulset/mongo --timeout=120s
kubectl rollout status -n weekend-k8s-lab deployment/backend --timeout=120s

# mongo-seed Job: 대기 → product_details 50개 upsert → reviews 3~10개씩 insert
kubectl wait -n weekend-k8s-lab --for=condition=complete --timeout=180s job/mongo-seed
kubectl logs -n weekend-k8s-lab job/mongo-seed
# fetched 50 product ids from postgres
# upserted 50 product_details docs
# inserted N reviews (skipped 0 products already seeded)
```

> mongo-seed 가 재기동될 때 (예: backoffLimit 안에서 postgres 미준비) 도 idempotent — product_details 는 upsert, reviews 는 product_id 별 존재 체크.

## 3) AC 검증

### [AC1] Mongo StatefulSet shape

```bash
kubectl get statefulset/mongo -n weekend-k8s-lab \
  -o jsonpath='replicas={.spec.replicas} node={.spec.template.spec.nodeSelector.kubernetes\.io/hostname}{"\n"}requests={.spec.template.spec.containers[0].resources.requests}{"\n"}limits={.spec.template.spec.containers[0].resources.limits}{"\n"}'
# replicas=1 node=worker-node2
# requests={"cpu":"100m","memory":"512Mi"}
# limits={"cpu":"500m","memory":"768Mi"}

kubectl get pv mongo-pv -o jsonpath='{.spec.nodeAffinity}{"\n"}'
# nodeSelectorTerms 에 worker-node2
```

### [AC2] Seed 결과

```bash
kubectl exec -n weekend-k8s-lab mongo-0 -- mongosh -u lab -p lab-dev-only \
  --authenticationDatabase admin --quiet --eval '
  const db = db.getSiblingDB("weekend");
  print("details=" + db.product_details.countDocuments());
  print("reviews=" + db.reviews.countDocuments());
  print("reviews_per_product_min=" + db.reviews.aggregate([
    {$group:{_id:"$product_id",c:{$sum:1}}},
    {$group:{_id:null,m:{$min:"$c"},M:{$max:"$c"}}}
  ]).toArray()[0].m);
'
# details=50
# reviews=N (in 150..500 range)
# reviews_per_product_min=3 (and max <= 10 expected)
```

### [AC3 / AC4 — cluster-internal 대체 (외부 URL은 #2 까지 deferred)]

```bash
kubectl -n weekend-k8s-lab port-forward svc/backend 18080:80 >/tmp/pf.log 2>&1 &
PF=$!
trap "kill $PF 2>/dev/null || true" EXIT
sleep 2

# 첫 product id 하나 잡아서
PID=$(curl -fsS http://127.0.0.1:18080/api/products | python3 -c 'import json,sys;print(json.load(sys.stdin)[0]["id"])')
echo "pid=$PID"

# detail merge
curl -fsS http://127.0.0.1:18080/api/products/$PID | python3 -m json.tool
# {
#   "id": "...",
#   "name": "...",
#   "price_cents": 51500,
#   "thumbnail": "...",
#   "description": "The ... is a flagship-grade ...",
#   "specs": [{"key":"sensor","value":"..."}, ...],
#   "reviews": [{"author":"...","rating":4,"body":"..."}, ...]
# }
```

### [AC4] event_log per-product 형태

```bash
BEFORE=$(kubectl exec -n weekend-k8s-lab postgres-0 -- psql -U lab -d weekend -At -c "SELECT count(*) FROM event_log;")
curl -fsS http://127.0.0.1:18080/api/products/$PID >/dev/null
AFTER=$(kubectl exec -n weekend-k8s-lab postgres-0 -- psql -U lab -d weekend -At -c "SELECT count(*) FROM event_log;")
echo "before=$BEFORE after=$AFTER (expected delta=1)"

kubectl exec -n weekend-k8s-lab postgres-0 -- \
  psql -U lab -d weekend -c \
  "SELECT event_type, payload->>'product_id' AS pid FROM event_log ORDER BY id DESC LIMIT 1;"
# event_type='product_viewed', pid=<$PID>
```

또한 #5 는 #4 의 batch event 를 대체했으므로 `/api/products` list call 은 더 이상 event_log 에 쓰지 않는다 — 검증:

```bash
BEFORE=$(kubectl exec -n weekend-k8s-lab postgres-0 -- psql -U lab -d weekend -At -c "SELECT count(*) FROM event_log;")
curl -fsS http://127.0.0.1:18080/api/products >/dev/null
curl -fsS http://127.0.0.1:18080/api/products >/dev/null
AFTER=$(kubectl exec -n weekend-k8s-lab postgres-0 -- psql -U lab -d weekend -At -c "SELECT count(*) FROM event_log;")
echo "before=$BEFORE after=$AFTER (expected delta=0 — list 은 event 안 씀)"
```

### [AC5] Mongo detail 누락 시 graceful

```bash
# 의도적으로 한 product 의 detail 만 지움
kubectl exec -n weekend-k8s-lab mongo-0 -- mongosh -u lab -p lab-dev-only \
  --authenticationDatabase admin --quiet --eval "
  const db = db.getSiblingDB('weekend');
  db.product_details.deleteOne({product_id:'$PID'});
  db.reviews.deleteMany({product_id:'$PID'});
"

curl -fsS http://127.0.0.1:18080/api/products/$PID | python3 -m json.tool
# description: "", specs: [], reviews: [] — 200 OK, 500 아님
```

검증 끝나면 seed Job 한 번 더 돌려서 복원:
```bash
kubectl delete job/mongo-seed -n weekend-k8s-lab
kubectl apply -k k8s/base/mongo
kubectl wait --for=condition=complete --timeout=120s -n weekend-k8s-lab job/mongo-seed
```

## 트러블슈팅

| 증상 | 원인 | 조치 |
|---|---|---|
| mongo-0 `OOMKilled` 초기 | WiredTiger cache 캡 누락 | `kubectl describe pod mongo-0` 의 args 에 `--wiredTigerCacheSizeGB=0.4` 있는지 확인 |
| mongo-seed `connection refused` 반복 | mongo Pod 아직 Running 아님 | `kubectl get pod mongo-0 -w` 로 Ready 대기, seed Job 의 backoffLimit 5 안에 진입하면 자동 복구 |
| backend `/api/products/{id}` 500, log `MONGO_*` KeyError | backend Pod 가 v1 그대로 (rollout 미반영) | `kubectl get pod -l app=backend -o jsonpath='{.items[0].spec.containers[0].image}'` 로 v2 확인, `kubectl rollout restart deploy/backend` |
| reviews 가 0개 | seed Job 실패했지만 reviews 컬렉션 인덱스만 생성 | `kubectl logs job/mongo-seed` 확인 후 delete + 재apply |
