# Security and production-readiness review

## Finding 1: Secrets management
- Risk and evidence: The original setup had the PostgreSQL password hardcoded in `docker-compose.yml` (line 26) and baked into the Docker image via `COPY config/app.env`. Anyone with access to the image or repo history could extract credentials.
- Impact: Full database access if credentials are leaked
- Implemented fix / commit: Moved password to `.env` (gitignored), used `${POSTGRES_PASSWORD}` substitution. Removed `COPY config/app.env` from Dockerfile. Commits: 0b3f53e, bf772be
- Production follow-up: Use Docker secrets, a secrets manager (Vault, AWS Secrets Manager), or CI/CD-injected environment variables
- How to verify: `docker history <image>` shows no secret layers. `git log -p` confirms no passwords in committed files.

## Finding 2: Container runs as non-root
- Risk and evidence: Original Dockerfile had `USER root`. A compromised app running as root inside the container could escape to the host or modify system files.
- Impact: Container escape, privilege escalation
- Implemented fix / commit: Changed `USER root` to `USER app` (UID 10001). Commit: bf772be
- Production follow-up: Add `read_only: true` to compose, use `no-new-privileges` security option
- How to verify: `docker exec app-01 whoami` returns `app`, not `root`

## Finding 3: Published ports — only NGINX exposed
- Risk and evidence: Original setup published PostgreSQL (15432) and Redis (16379) on the host. Direct database access bypasses application-level controls.
- Impact: Unauthorized database access, data exfiltration
- Implemented fix / commit: Removed `ports` from postgres and redis services. Only NGINX port 8080 is published. Commit: 6171374
- Production follow-up: Use firewall rules to further restrict access to port 8080
- How to verify: `docker compose ps` shows no published ports for postgres or redis. `docker inspect postgres --format '{{json .NetworkSettings.Ports}}'` shows null bindings.

## Finding 4: Network isolation
- Risk and evidence: NGINX was on the `backend` network, giving it direct access to PostgreSQL and Redis. A compromised NGINX could query the database directly.
- Impact: Data access bypass, lateral movement
- Implemented fix / commit: Removed NGINX from backend network. Commit: 14f4ebb
- Production follow-up: Add network policies, implement mutual TLS between services
- How to verify: `docker inspect nginx` shows only the frontend network. `docker exec nginx ping postgres` fails.

## Finding 5: Database backup and recovery
- Risk and evidence: No backup mechanism existed in the original setup. Data loss from volume corruption, accidental deletion, or failed upgrade would be unrecoverable.
- Impact: Complete data loss
- Implemented fix / commit: Created `backup.sh` (pg_dump) and `restore.sh` (pg_restore). Commit: 15b07d2
- Production follow-up: Schedule automated backups (cron), store backups off-host (S3, GCS), test restores regularly, implement point-in-time recovery with WAL archiving
- How to verify: Run `./backup.sh`, destroy and recreate postgres, run `./restore.sh`, verify records exist
