# Troubleshooting journal

## Entry 1 
- Symptom: All containers failing to start, healthchecks failing
- Hypothesis: Healthcheck endpoint might be wrong
- Command or test: `docker compose -p barq-assessment logs app-01`
- Actual output: Healthcheck hitting `/healthz` which doesn't exist (app has `/health`)
- Failed attempt and what changed your thinking: N/A — the typo was visible in the compose file
- Root cause: Healthcheck path was `/healthz` instead of `/health`
- Fix: Changed healthcheck URL to `http://127.0.0.1:8080/health`
- Retest evidence: `docker compose ps` showed app containers as healthy
- Related commit: a23ac46
- Remaining uncertainty: None

## Entry 2 
- Symptom: App containers unhealthy, connection refused in healthcheck
- Hypothesis: App might be listening on wrong interface
- Command or test: `docker exec app-01 python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health')"`
- Actual output: Connection refused — the app was bound to `127.0.0.1` inside the container, but the original `APP_HOST` was also `127.0.0.1`. Checked compose and found `APP_HOST: "127.0.0.1"`
- Failed attempt and what changed your thinking: N/A
- Root cause: `APP_HOST` was set to `127.0.0.1`, making the app listen only on loopback inside the container. Other containers (and NGINX) couldn't reach it.
- Fix: Changed `APP_HOST` to `0.0.0.0` to bind to all interfaces
- Retest evidence: `curl http://127.0.0.1:8080/` returned 200 after rebuild
- Related commit: 53a82f0
- Remaining uncertainty: None

## Entry 3 
- Symptom: NGINX returning 502 Bad Gateway
- Hypothesis: NGINX might be proxying to wrong port on app containers
- Command or test: `docker compose -p barq-assessment logs nginx` — showed upstream connection failures
- Actual output: NGINX was trying to connect to `app-01:8081` but app listens on `8080`
- Failed attempt and what changed your thinking: N/A
- Root cause: `nginx.conf` had `server app-01:8081` instead of `server app-01:8080`
- Fix: Changed upstream to `app-01:8080`
- Retest evidence: `curl http://127.0.0.1:8080/` returned valid JSON response
- Related commit: 31fc3f3
- Remaining uncertainty: None

## Entry 4
- Symptom: NGINX port mapping not working, container port mismatch
- Hypothesis: Docker port mapping might target wrong container port
- Command or test: Checked `docker-compose.yml` — saw `ports: ["127.0.0.1:${PUBLIC_PORT:-8080}:81"]`
- Actual output: NGINX listens on port 80 inside the container, but compose was mapping to port 81
- Failed attempt and what changed your thinking: N/A
- Root cause: Container port was `81` instead of `80`
- Fix: Changed to `"127.0.0.1:${PUBLIC_PORT:-8080}:80"`
- Retest evidence: `curl http://127.0.0.1:8080/` worked
- Related commit: 44adee3
- Remaining uncertainty: None

## Entry 5
- Symptom: Both app instances returning same `instance_id: "app-01"`
- Hypothesis: INSTANCE_ID environment variable might be duplicated
- Command or test: Checked `docker-compose.yml` — both app-01 and app-02 had `INSTANCE_ID: "app-01"`
- Actual output: app-02 service had `INSTANCE_ID: "app-01"` instead of `"app-02"`
- Failed attempt and what changed your thinking: N/A
- Root cause: Copy-paste error in the compose file
- Fix: Changed app-02's `INSTANCE_ID` to `"app-02"`
- Retest evidence: Repeated `curl /instance` showed both `app-01` and `app-02`
- Related commit: a23ac46
- Remaining uncertainty: None

## Entry 6 
- Symptom: PostgreSQL and Redis publishing ports on host (15432 and 16379)
- Hypothesis: These ports shouldn't be exposed per task requirements
- Command or test: `docker compose -p barq-assessment ps` showed published ports for postgres and redis
- Actual output: postgres had `127.0.0.1:15432->5432`, redis had `127.0.0.1:16379->6379`
- Failed attempt and what changed your thinking: N/A
- Root cause: Compose file had `ports` directives on postgres and redis services
- Fix: Removed `ports` from both postgres and redis services
- Retest evidence: `docker compose ps` no longer showed published ports for these services
- Related commit: 6171374
- Remaining uncertainty: None

## Entry 7 
- Symptom: `DATABASE_URL` had wrong password and port, `REDIS_URL` had wrong port
- Hypothesis: Connection strings might have typos
- Command or test: Compared `config/app.env` values with `docker-compose.yml` postgres settings
- Actual output: Password was `BarqLabOnly_7qN2vK8d` (should be `c`), postgres port was `5433` (should be `5432`), redis port was `6380` (should be `6379`)
- Failed attempt and what changed your thinking: N/A
- Root cause: Intentional typos in the connection strings
- Fix: Corrected password to `BarqLabOnly_7qN2vK8c`, postgres port to `5432`, redis port to `6379`
- Retest evidence: `/ready` endpoint showed both postgres and redis as `ready`
- Related commit: 0c29ee7
- Remaining uncertainty: None

## Entry 8 
- Symptom: PostgreSQL data lost on every container restart
- Hypothesis: Data might not be persisting to the named volume
- Command or test: `docker compose -p barq-assessment down && docker compose -p barq-assessment up -d` — records gone
- Actual output: Records created via `/records` disappeared after restart
- Failed attempt and what changed your thinking: Initially checked if the volume existed — it did, but was mounted to wrong path
- Root cause: Two issues: (1) named volume mounted to `/var/lib/postgresql/backup` instead of `/var/lib/postgresql/data`, (2) `tmpfs: [/var/lib/postgresql/data]` was overlaying the real data directory with a RAM-based filesystem
- Fix: Changed volume mount to `/var/lib/postgresql/data` and removed the `tmpfs` directive
- Retest evidence: Created a record, restarted postgres, record survived
- Related commit: a964446
- Remaining uncertainty: None

## Entry 9
- Symptom: NGINX could reach PostgreSQL and Redis directly (no network isolation)
- Hypothesis: NGINX might be on the backend network
- Command or test: `docker inspect nginx --format '{{json .NetworkSettings.Networks}}'`
- Actual output: NGINX was connected to both `frontend` and `backend` networks
- Failed attempt and what changed your thinking: N/A
- Root cause: Compose file had `networks: [frontend, backend]` for nginx
- Fix: Changed to `networks: [frontend]`
- Retest evidence: `docker inspect nginx` showed only frontend network
- Related commit: 14f4ebb
- Remaining uncertainty: None

## Entry 10
- Symptom: When one app backend was stopped, half of all requests failed with 502
- Hypothesis: NGINX failover might be disabled
- Command or test: Stopped app-02, sent requests — ~50% returned 502
- Actual output: NGINX was not retrying failed requests on the other backend
- Failed attempt and what changed your thinking: Checked NGINX docs — `proxy_next_upstream off` disables all failover
- Root cause: `proxy_next_upstream off` in nginx.conf disabled upstream failover. Also `max_fails=0` prevented NGINX from marking dead backends
- Fix: Changed to `proxy_next_upstream error timeout http_502 http_503` with `proxy_next_upstream_tries 2`, and `max_fails=2 fail_timeout=10s`
- Retest evidence: Stopped app-02, all requests succeeded via app-01
- Related commit: ef95606
- Remaining uncertainty: None

## Entry 11
- Symptom: `video_challenge.sh` failed with "every service must be healthy and unpaused"
- Hypothesis: Maybe not all services have healthchecks
- Command or test: `docker inspect nginx --format '{{.State.Health.Status}}'` — returned empty
- Actual output: nginx had no healthcheck configured, so Docker reported no health status
- Failed attempt and what changed your thinking: Initially thought all services were healthy because `docker compose ps` showed them as "Up" — but "Up" is not the same as "healthy"
- Root cause: The video challenge script checks `Health.Status == "healthy"` for all 5 services. nginx had no healthcheck defined.
- Fix: Added healthcheck using `wget` (available in alpine image): `wget -qO /dev/null http://127.0.0.1:80/`
- Retest evidence: `docker inspect nginx --format '{{.State.Health.Status}}'` returned `healthy`, video challenge passed preflight
- Related commit: 4e9260f
- Remaining uncertainty: None
