# Runbook: in-cluster registry를 insecure로 신뢰시키기

> **대상 환경:** kubeadm 1.36.0 + containerd 2.2.4, VirtualBox VM 3대
> (`master-node` 192.168.56.105, `worker-node1` 192.168.56.106, `worker-node2` 192.168.56.107).
> in-cluster registry는 plain HTTP(`NodePort 30500`)로 노출되며, TLS는 1일 학습 프로젝트 범위에서 의도적으로 생략한다.

## 왜 필요한가

`k8s/base/registry/` 의 `registry:2` 컨테이너는 TLS 없이 5000번 포트에서 HTTP로 응답한다.
Docker / containerd 클라이언트는 기본적으로 HTTPS로 접속하므로, 양쪽 모두에서 `192.168.56.105:30500` 을 **insecure registry**로 명시해야 push / pull 이 가능하다.

| 클라이언트 | 역할 | 적용 대상 |
|---|---|---|
| Docker daemon | `docker build` / `docker push` 수행 | **master-node 1대** |
| containerd | Pod 스케줄링 시 image pull | **3개 노드 전부** |

레지스트리 주소는 worker-node1에 핀된 Pod로 라우팅되지만, NodePort라서 어느 노드의 IP를 써도 무방하다. 일관성을 위해 `192.168.56.105:30500`(master-node IP) 으로 통일한다.

---

## B-1. master-node Docker daemon 설정

master-node에 SSH로 접속해서:

```bash
# 기존 daemon.json 백업 (없으면 무시)
sudo cp /etc/docker/daemon.json /etc/docker/daemon.json.bak 2>/dev/null || true

# insecure-registries 등록
# 주의: 기존 daemon.json에 다른 키가 있으면 이 명령은 덮어쓴다. 그런 경우 수동으로 병합할 것.
sudo tee /etc/docker/daemon.json >/dev/null <<'EOF'
{
  "insecure-registries": ["192.168.56.105:30500"]
}
EOF

sudo systemctl restart docker
```

**검증:**

```bash
docker info | grep -A2 'Insecure Registries'
# Insecure Registries:
#   192.168.56.105:30500
#   127.0.0.0/8

docker pull hello-world
docker tag hello-world:latest 192.168.56.105:30500/hello-world:v1
docker push 192.168.56.105:30500/hello-world:v1
# v1: digest: sha256:... size: ...

curl -s http://192.168.56.105:30500/v2/_catalog
# {"repositories":["hello-world"]}
```

---

## B-2. 3개 노드 containerd 설정

`master-node`, `worker-node1`, `worker-node2` **각각**에서 동일하게 실행한다.

### 1) hosts.d 디렉터리가 활성화돼 있는지 확인

```bash
sudo grep -E 'config_path\s*=' /etc/containerd/config.toml
```

`config_path = "/etc/containerd/certs.d"` 가 보이면 2)로 넘어간다.
보이지 않거나 빈 문자열(`""`)이면 `/etc/containerd/config.toml` 의 registry 블록을 편집한다.
containerd 2.x 에서는 CRI 플러그인이 분리됐기 때문에 키 경로가 두 가지 형태 중 하나일 수 있다:

```toml
# containerd 2.x 표준 (CRI plugin 분리 후)
[plugins.'io.containerd.cri.v1.images'.registry]
  config_path = '/etc/containerd/certs.d'

# 또는 v1.x 호환 경로 (예전 config를 그대로 쓰는 경우)
[plugins."io.containerd.grpc.v1.cri".registry]
  config_path = "/etc/containerd/certs.d"
```

자기 노드의 `config.toml` 에 **이미 존재하는 섹션**의 `config_path` 만 위 값으로 채우면 된다. 둘 다 추가하지 말 것.

### 2) registry별 hosts.toml 작성

```bash
sudo mkdir -p '/etc/containerd/certs.d/192.168.56.105:30500'
sudo tee '/etc/containerd/certs.d/192.168.56.105:30500/hosts.toml' >/dev/null <<'EOF'
server = "http://192.168.56.105:30500"

[host."http://192.168.56.105:30500"]
  capabilities = ["pull", "resolve"]
EOF
```

> `server` 의 스킴이 `http://` 이면 containerd 가 HTTPS 시도 없이 바로 HTTP로 접속한다.
> 따라서 `skip_verify` (TLS 검증 우회 옵션)는 필요하지 않다.

### 3) containerd 재시작

```bash
sudo systemctl restart containerd
sudo systemctl status containerd --no-pager | head -10
```

### 4) 노드별 단발 검증 (선택)

```bash
sudo ctr -n k8s.io images pull --plain-http 192.168.56.105:30500/hello-world:v1
# unpacking linux/amd64 sha256:... done
```

`ctr` 은 `--plain-http` 플래그 없이는 `hosts.toml` 을 거치지 않고 직접 HTTPS로 시도한다.
따라서 위 명령의 성공은 "registry에 image가 있다" 만 보장하며, `hosts.toml` 자체의 동작 검증은 다음 단계의 Pod 풀로 한다.

---

## 최종 검증: Pod 스케줄링으로 풀 테스트

`kubectl` 이 설정된 곳(보통 master-node)에서:

```bash
kubectl run pull-test \
  --image=192.168.56.105:30500/hello-world:v1 \
  --image-pull-policy=Always \
  --restart=Never \
  -n weekend-k8s-lab

kubectl get pod pull-test -n weekend-k8s-lab -o wide
# STATUS = Completed (hello-world는 한 줄 출력 후 종료)
# NODE  = 스케줄링된 노드 이름

kubectl describe pod pull-test -n weekend-k8s-lab | grep -A6 Events
# Events 에 "Pulling image" → "Successfully pulled" → "Started" 가 순서대로 보여야 함
```

다른 노드에서도 풀 가능한지 확인하려면 `pull-test` 를 지우고 `nodeSelector` 를 바꿔가며 다시 띄운다.

```bash
kubectl delete pod pull-test -n weekend-k8s-lab
```

---

## 트러블슈팅

| 증상 | 어디서 보임 | 원인 | 조치 |
|---|---|---|---|
| `http: server gave HTTP response to HTTPS client` | `docker push` | B-1 미적용 또는 daemon 재시작 누락 | `docker info \| grep -A2 'Insecure Registries'` 확인 후 `systemctl restart docker` |
| `failed to do request ... tls: first record does not look like a TLS handshake` | `kubectl describe pod` Events | 해당 노드에 B-2 미적용 또는 containerd 미재시작 | 해당 노드에서 `cat /etc/containerd/certs.d/192.168.56.105:30500/hosts.toml`, `systemctl status containerd` |
| `ErrImagePull: ... repository ... not found` | Pod Events | 이미지 태그 오타 또는 push 누락 | `curl -s http://192.168.56.105:30500/v2/_catalog`, `curl -s http://192.168.56.105:30500/v2/<name>/tags/list` |
| `config_path` 변경했는데도 무시됨 | `ctr` / Pod | `config.toml` 안에 registry 섹션이 두 군데(`v1.cri` + `cri.v1.images`) 중복 정의 | 한쪽만 남기고 다른 쪽 삭제 후 containerd 재시작 |
| Pod 가 `Pending` 으로만 머묾 | `kubectl describe pod` Events | 이미지 풀이 아니라 스케줄링 단계 문제 (taint, resource 등) | 이미지 풀 이슈와 무관 — 별도 진단 |

---

## 롤백

### B-1 (master-node)
```bash
sudo mv /etc/docker/daemon.json.bak /etc/docker/daemon.json 2>/dev/null \
  || sudo rm /etc/docker/daemon.json
sudo systemctl restart docker
```

### B-2 (각 노드별)
```bash
sudo rm -rf '/etc/containerd/certs.d/192.168.56.105:30500'
sudo systemctl restart containerd
```

`config_path` 설정 자체는 빈 디렉터리를 가리켜도 무해하므로 그대로 두어도 된다.
