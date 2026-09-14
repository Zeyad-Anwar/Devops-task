# BARQ DevOps Assessment

Flask API with PostgreSQL and Redis, running behind NGINX with two (or three) app instances.

## Prerequisites

- Linux or WSL2
- Python 3.12, Git
- Docker with Compose (Linux containers)
- 2 CPU cores, 4 GB RAM, 3 GB disk free

## Setup

```bash
git clone <repository-url>
cd BARQ-Academy
cp .env.example .env
# Edit .env and set POSTGRES_PASSWORD to your lab password
```

## Build and start

```bash
docker compose -p barq-assessment up --build -d
```

Wait for all services to become healthy:

```bash
docker compose -p barq-assessment ps -a
```

## Test endpoints

```bash
curl -i http://127.0.0.1:8080/
curl -i http://127.0.0.1:8080/health
curl -i http://127.0.0.1:8080/ready
curl -i http://127.0.0.1:8080/instance
curl -H 'Content-Type: application/json' -d '{"title":"Test record"}' http://127.0.0.1:8080/records
curl http://127.0.0.1:8080/records
curl http://127.0.0.1:8080/counter
```

Verify both backends respond:

```bash
for i in $(seq 1 10); do
  curl -s http://127.0.0.1:8080/instance | python3 -c "import sys,json; print(json.load(sys.stdin)['instance_id'])"
done
```

## Run validation

```bash
python3 validate.py
```

## Run failure test

```bash
python3 failure_test.py
```

## Backup PostgreSQL

```bash
./backup.sh
```

Backups are saved to `backups/barq_tasks_<timestamp>.dump`.

## Restore PostgreSQL

```bash
# Restore latest backup
./restore.sh

# Or specify a backup file
./restore.sh backups/barq_tasks_20260913_120000.dump
```

## Prove persistence

```bash
# Create a record
curl -H 'Content-Type: application/json' -d '{"title":"Persistence proof"}' http://127.0.0.1:8080/records

# Recreate containers (keeps volumes)
docker compose -p barq-assessment up -d --force-recreate postgres app-01 app-02

# Wait for healthy
docker compose -p barq-assessment ps -a

# Verify the record survived
curl http://127.0.0.1:8080/records
```

## Change public port (e.g. 8080 → 8090)

```bash
# Edit .env
sed -i 's/PUBLIC_PORT=8080/PUBLIC_PORT=8090/' .env

# Recreate nginx with new port
docker compose -p barq-assessment up -d nginx

# Verify
curl http://127.0.0.1:8090/health
```

## Add a third app instance

Add `app-03` service to `docker-compose.yml` and its upstream entry to `nginx/nginx.conf`, then:

```bash
docker compose -p barq-assessment up -d --build app-03
docker exec nginx nginx -s reload
```

## Stop

```bash
docker compose -p barq-assessment down
```

## Cleanup (removes volumes and all data)

```bash
docker compose -p barq-assessment down --volumes
```

## Questions

### What failed first?
The app containers failed to start because `APP_HOST` was set to `127.0.0.1`, making the app only listen on loopback inside the container — unreachable from other containers. The healthcheck also had a typo (`/healthz` instead of `/health`).

### What proved the cause?
Running `docker compose logs` showed connection refused errors. Checking the healthcheck endpoint with `docker exec` confirmed it was hitting a non-existent path.

### Which failed attempt taught you something?
Initially tried to fix networking by adjusting port mappings, but the real issue was the bind address. This taught me to check what address a service is listening on inside the container. Also this is my first time working with NGINX so i learned alot of what it is and how it works.

### How do requests flow?
Client → host:8080 → NGINX:80 (frontend network) → app-01/app-02:8080 (frontend+backend networks) → postgres:5432 / redis:6379 (backend network).

### Why these ports, networks and readiness checks?
Port 8080 is the only published port (via NGINX). Two networks isolate traffic: frontend (NGINX↔apps) and backend (apps↔databases, marked `internal: true`). Readiness checks verify actual database connectivity, not just process liveness.

### Why these timeouts, retries, restart settings and resource limits?
- `proxy_connect_timeout 2s` / `proxy_read_timeout 3s`: short enough to fail fast, long enough for normal operations
- `max_fails=2 fail_timeout=10s`: marks backend down after 2 failures, retries after 10s
- `restart: unless-stopped`: auto-recovery from crashes without interfering with manual stops
- Memory limits (256M apps/postgres, 128M redis/nginx): prevents any service from consuming all host memory

### When should validation fail?
When any endpoint is unreachable, any dependency is not ready, only one backend responds, network isolation is broken, or prohibited ports are published.

### Which single points of failure remain?
- Single NGINX instance (no HA proxy)
- Single PostgreSQL instance (no replication)
- Single Redis instance (no sentinel/cluster)

### How would you fix them in production?
Use a managed load balancer, PostgreSQL streaming replication with automatic failover and Redis Sentinel or Cluster
