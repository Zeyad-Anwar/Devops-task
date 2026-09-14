# Technical decisions

## Decision 1: Two-network isolation — frontend and backend
- Choice: NGINX on `frontend` only; apps on both `frontend` and `backend`; databases on `backend` only (marked `internal: true`)
- Why: This prevents NGINX from directly accessing PostgreSQL or Redis. The `internal: true` flag on backend blocks all external access to database services. Apps bridge both networks.
- Alternative: Single flat network with firewall rules
- Trade-off: More complex compose config, but enforced at the Docker network level — no misconfiguration can leak database access through NGINX
- Evidence / commit: 14f4ebb
- Production improvement: Add network policies in Kubernetes for finer-grained control

## Decision 2: NGINX failover — proxy_next_upstream with retry
- Choice: `proxy_next_upstream error timeout http_502 http_503` with `proxy_next_upstream_tries 2` and `max_fails=2 fail_timeout=10s`
- Why: Allows NGINX to retry a failed request on the next healthy backend, ensuring availability when one app goes down. `max_fails=2` gives a backend two chances before marking it down for 10 seconds.
- Alternative: `proxy_next_upstream off` (original) — simpler but no resilience
- Trade-off: Non-idempotent POST requests could be retried, potentially causing duplicates. Mitigated by only retrying on connection-level errors (502/503), not on application errors.
- Evidence / commit: ef95606
- Production improvement: Use `non_idempotent` flag carefully, add circuit breakers

## Decision 3: Restart policy — unless-stopped
- Choice: `restart: unless-stopped` for all services
- Why: Containers automatically recover from crashes and survive Docker daemon restarts. Unlike `always`, it respects manual `docker stop` commands.
- Alternative: `on-failure` — only restarts on non-zero exit. `always` — restarts even after manual stop.
- Trade-off: A crash-looping container will keep restarting. In production you'd want monitoring to detect this.
- Evidence / commit: e8272e7
- Production improvement: Add `restart_policy.max_attempts` or use an orchestrator with proper crash loop backoff

## Decision 4: Secret management — .env file with variable substitution
- Choice: Moved `POSTGRES_PASSWORD` to `.env` (gitignored) and referenced via `${POSTGRES_PASSWORD}` in compose
- Why: Keeps secrets out of the compose file, Dockerfile, and git history. The `.env` file is in `.gitignore`. A safe `.env.example` with `changeme` is committed for documentation.
- Alternative: Docker secrets, HashiCorp Vault, or environment-specific CI/CD injection
- Trade-off: `.env` files are simple but still plaintext on disk. Better than committed secrets but not production-grade.
- Evidence / commit: 0b3f53e
- Production improvement: Use Docker secrets or a secrets manager. Never store passwords in plaintext files.

## Decision 5: Redis persistence — AOF + RDB snapshots
- Choice: Enabled both `--appendonly yes` and `--save 60 1` with a named volume
- Why: AOF logs every write for durability. RDB snapshots provide periodic backups. The counter data (`/counter` endpoint) is preserved across restarts.
- Alternative: AOF only, RDB only, or no persistence (original)
- Trade-off: Slightly more disk I/O. For a simple counter, this is sufficient without needing `appendfsync always`.
- Evidence / commit: 2b5a0f3
- Production improvement: Use Redis Sentinel for HA, configure `appendfsync everysec` for better durability
