# OCI 배포

Oracle Cloud Always Free 의 **Ampere A1** VM 한 대에 이 앱만 올린다.
다른 프로젝트와 VM 을 나누는 이유: 한쪽이 메모리를 먹거나 재시작해도 다른 쪽이
흔들리지 않아야 한다. A1 무료 풀(4 OCPU / 24GB)을 쪼개면 둘 다 무료로 들어간다.

이 앱은 **1 OCPU / 6GB 면 충분**하다 (SQLite · 담당자 350명 규모).

```
테넌시
├─ 압축함 dealflow          ← 권한·비용 경계
│   └─ VM  A1  1 OCPU / 6GB  + 블록 볼륨 50GB
└─ 압축함 <다른 프로젝트>
    └─ VM  A1  나머지
```

> 압축함(compartment)은 IAM·청구 경계일 뿐 런타임을 나누지 않는다.
> 프로세스·디스크까지 나누려면 **VM 을 나눠야** 한다.

---

## 0. 먼저 확인 — A1 풀에 자리가 있는가

다른 프로젝트가 이미 A1 을 쓰고 있으므로 남은 용량부터 본다.
콘솔 › **Governance › Limits, Quotas and Usage** › 서비스 `Compute` ›
`Cores for Ampere A1` 에서 남은 수를 확인한다.

- **1 OCPU 이상 남음** → 아래 순서대로 새 VM 을 만든다.
- **자리가 없음** → 기존 VM 에 얹는다. `docker-compose.prod.yml` 을 그대로 쓰되
  Caddy 는 기존 것을 쓰고 `web` 만 올린 뒤, 기존 Caddyfile 에
  `Caddyfile` 의 사이트 블록을 복사해 붙인다(도메인이 다르므로 충돌하지 않는다).

---

## 1. 도메인 (DuckDNS)

1. <https://www.duckdns.org> 에서 GitHub 로 로그인
2. 원하는 이름을 잡는다 → `<이름>.duckdns.org`
3. VM 을 만든 뒤 **공인 IP** 를 그 이름에 넣는다

> IP 가 바뀌어도 이름은 그대로라 각자 PC 의 에이전트를 다시 손보지 않아도 된다.
> 나중에 회사 도메인으로 갈아탈 때도 이 이름을 CNAME 으로 넘기면 된다.

---

## 2. VM 만들기

- **이미지**: Canonical Ubuntu 24.04 (**aarch64**)
- **모양**: `VM.Standard.A1.Flex` · 1 OCPU · 6 GB
- **네트워킹**: 공인 IP 할당
- **SSH 키**: 직접 만든 키 등록

### 방화벽 두 곳을 다 열어야 한다

OCI 는 **보안 목록**과 **인스턴스 안 iptables** 가 따로 논다. 하나만 열면
연결이 조용히 막히고, 원인을 찾는 데 시간이 간다.

```bash
# 1) 콘솔: VCN › 보안 목록 › 수신 규칙 추가
#    0.0.0.0/0  TCP  80,443

# 2) 인스턴스 안에서
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
```

앱 포트(8000)는 **열지 않는다.** Caddy 만 밖을 보고, 앱은 도커 내부에만 있다.

---

## 3. 블록 볼륨 — 명단이 사는 곳

부트 볼륨에 DB 를 두면 인스턴스를 다시 만들 때 명단이 통째로 사라진다.

```bash
# 콘솔에서 50GB 블록 볼륨을 만들어 인스턴스에 붙인 뒤(iSCSI 명령은 콘솔이 알려준다)
lsblk                                   # 예: /dev/sdb
sudo mkfs.ext4 /dev/sdb
sudo mkdir -p /mnt/dealflow
echo '/dev/sdb /mnt/dealflow ext4 defaults,_netdev,nofail 0 2' | sudo tee -a /etc/fstab
sudo mount -a
sudo mkdir -p /mnt/dealflow/data
```

`_netdev,nofail` 이 없으면 볼륨이 늦게 붙는 재부팅에서 부팅이 멈춘다.

---

## 4. 도커 + 코드

```bash
sudo apt update && sudo apt install -y docker.io docker-compose-v2 git
sudo usermod -aG docker $USER && newgrp docker
sudo systemctl enable --now docker          # 재부팅 후 자동 기동

git clone https://github.com/BBlack-Hun/dealflow-workspace.git
cd dealflow-workspace
cp deploy/.env.example deploy/.env
```

`deploy/.env` 를 채운다. **비우면 서버가 뜨지 않는다** (`app/config.py`
`assert_ready`) — 저장소가 공개라 기본 비밀번호는 이미 아무나 아는 값이다.

```bash
openssl rand -hex 24        # DEALFLOW_AGENT_TOKEN 에 넣을 값
```

---

## 5. 데이터 옮기기

**`dealflow.db` 파일만 복사하면 안 된다.** WAL 모드라 방금 쓴 것이 아직 본체가
아니라 `-wal` 에 있을 수 있다. 체크포인트 직후면 맞고 쓰기 직후면 빠지는데,
어느 쪽인지는 복사하는 사람이 알 수 없다.

```bash
# 지금 서버(로컬)에서 — 멈출 필요 없다
docker compose exec web python scripts/db_snapshot.py \
    /app/data/dealflow.db /app/data/snapshot.db
docker compose cp web:/app/data/snapshot.db ./snapshot.db

# 옮기기
scp snapshot.db ubuntu@<공인IP>:/tmp/

# 받은 쪽에서 — 표별 행수·무결성·스키마 버전이 같은지 눈으로 본다
python3 scripts/db_snapshot.py --verify /tmp/snapshot.db

sudo mv /tmp/snapshot.db /mnt/dealflow/data/dealflow.db
```

> 옮긴 뒤에도 로컬에서 작업하면 그만큼이 서버에 없다.
> **넘어가는 시점을 정하고 한 번만** 뜬다. 그 뒤로는 서버가 원본이다.

---

## 6. 올리기

```bash
cd deploy
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml logs -f web
```

`RUN_MIGRATIONS=1` 이라 밀린 마이그레이션이 자동으로 붙는다.

```bash
curl -sS https://<이름>.duckdns.org/health      # {"status":"ok",...}
```

인증서 발급은 첫 요청에서 몇 초 걸린다. 실패하면 대개 80 번이 막힌 것이다
(3 번의 두 곳을 다 열었는지 확인).

---

## 7. 각자 PC 의 에이전트 돌리기

에이전트는 **재설치가 필요 없다.** `agent/config.yaml` 두 줄만 고치고 다시 켠다.

```yaml
server_url: "https://<이름>.duckdns.org"   # 127.0.0.1 → 서버 주소
token: "<웹 화면 [설정]에서 발급받은 값>"
```

토큰은 사람마다 다르다. 웹에서 로그인 → **설정** 화면에 자기 토큰이 있다.

---

## 8. 백업

DB 가 한 파일이라 백업도 한 줄이다. 스냅샷 API 를 쓰므로 돌아가는 중에 떠도 된다.

```bash
sudo tee /etc/cron.daily/dealflow-backup >/dev/null <<'EOF'
#!/bin/sh
cd /home/ubuntu/dealflow-workspace/deploy || exit 0
STAMP=$(date +%Y%m%d)
docker compose -f docker-compose.prod.yml exec -T web \
  python scripts/db_snapshot.py /app/data/dealflow.db /app/data/backup-$STAMP.db
find /mnt/dealflow/data -name 'backup-*.db' -mtime +14 -delete
EOF
sudo chmod +x /etc/cron.daily/dealflow-backup
```

블록 볼륨 스냅샷(콘솔 › Block Volumes › 백업 정책)도 함께 걸어 두면,
인스턴스가 통째로 날아가도 되살릴 수 있다.

---

## 도메인

`contactvc.duckdns.org` (DuckDNS · 서버 132.145.95.21)

IP 가 바뀌어도 이름은 그대로라, 각자 PC 의 에이전트를 다시 손보지 않아도 된다.

**이름 자체를 바꿀 때는 세 곳이 같이 움직여야 한다.** 하나라도 빠지면 화면은
멀쩡한데 발송만 조용히 멎는다 — 에이전트가 옛 주소를 계속 두드리기 때문이다.

1. 서버 `deploy/.env` 의 `DEALFLOW_DOMAIN` → `docker compose up -d --force-recreate caddy`
   (Caddy 가 새 이름으로 Let's Encrypt 인증서를 알아서 받는다. DNS 가 먼저
   이 서버를 가리키고 있어야 한다 — 아니면 발급이 실패하고 옛 인증서도 없다)
2. `.github/workflows/deploy.yml` 의 밖에서 확인하는 주소
3. **각자 PC 의 `agent/config.yaml` 의 `server_url`** — 자동으로 안 따라온다.
   이 파일은 PC 마다 따로 있어서 서버에서 밀어 넣을 방법이 없다.

옛 이름(`dealflow-imp.duckdns.org`)은 2026-09-01 에 여기서 떼어 냈다.
DuckDNS 페이지에서 IP 만 갱신하면 된다.

## 확인 목록

- [ ] `deploy/.env` 를 채웠다 (안 채우면 뜨지 않는다)
- [ ] 보안 목록 **과** iptables 둘 다 80/443 을 열었다
- [ ] DB 가 `/mnt/dealflow/data` (블록 볼륨)에 있다 — 부트 볼륨 아님
- [ ] `--verify` 로 옮기기 전후 행수가 같았다
- [ ] `https://` 로 열린다 (http 아님)
- [ ] 각자 PC 의 `agent/config.yaml` 을 새 주소로 고쳤다
- [ ] 첫 발송 전에 `DEALFLOW_TEST_ROOM` 으로 한 건 확인했다
