#!/usr/bin/env python3
"""Environment validation script with bounded waits, PASS/FAIL and non-zero failure exits."""
import json
import subprocess
import sys
import time
import urllib.request
import urllib.error

BASE_URL = "http://127.0.0.1:8080"
PROJECT = "barq-assessment"
TIMEOUT = 5
MAX_WAIT = 60

passed = 0
failed = 0


def check(name, condition, detail=""):
    """Record a PASS/FAIL result."""
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  {detail}")


def http_get(path):
    """Make an HTTP GET request, return (status_code, parsed_json) or (None, None)."""
    try:
        req = urllib.request.Request(f"{BASE_URL}{path}")
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = json.loads(resp.read().decode())
            return resp.status, body
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode())
        except Exception:
            body = None
        return e.code, body
    except Exception:
        return None, None


def http_post(path, data):
    """Make an HTTP POST request with JSON body."""
    try:
        req = urllib.request.Request(
            f"{BASE_URL}{path}",
            data=json.dumps(data).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = json.loads(resp.read().decode())
            return resp.status, body
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode())
        except Exception:
            body = None
        return e.code, body
    except Exception:
        return None, None


def docker(*args):
    """Run a docker command and return stdout."""
    result = subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=30
    )
    return result.stdout.strip(), result.returncode


def wait_for_ready():
    """Bounded wait for the environment to become ready."""
    print(f"\n[*] Waiting up to {MAX_WAIT}s for services to be ready...")
    start = time.time()
    while time.time() - start < MAX_WAIT:
        status, body = http_get("/ready")
        if status == 200 and body and body.get("status") == "ready":
            elapsed = round(time.time() - start, 1)
            print(f"    Services ready after {elapsed}s")
            return True
        time.sleep(2)
    print(f"    Timed out after {MAX_WAIT}s")
    return False


def check_public_access():
    """Check that the public URL is accessible."""
    print("\n[1] Public access")
    status, body = http_get("/")
    check("GET / returns 200", status == 200, f"got {status}")
    check("Response has message", body and "message" in body if body else False)


def check_all_endpoints():
    """Check all required endpoints."""
    print("\n[2] All endpoints")

    # /health
    status, body = http_get("/health")
    check("GET /health returns 200", status == 200, f"got {status}")

    # /ready
    status, body = http_get("/ready")
    check("GET /ready returns 200", status == 200, f"got {status}")
    if body:
        deps = body.get("dependencies", {})
        check("PostgreSQL is ready", deps.get("postgres") == "ready", f"got {deps.get('postgres')}")
        check("Redis is ready", deps.get("redis") == "ready", f"got {deps.get('redis')}")

    # /instance
    status, body = http_get("/instance")
    check("GET /instance returns 200", status == 200, f"got {status}")

    # /records GET
    status, body = http_get("/records")
    check("GET /records returns 200", status == 200, f"got {status}")

    # /records POST
    status, body = http_post("/records", {"title": "Validation test"})
    check("POST /records returns 201", status == 201, f"got {status}")

    # /counter
    status, body = http_get("/counter")
    check("GET /counter returns 200", status == 200, f"got {status}")
    check("/counter has counter value", body and isinstance(body.get("counter"), int) if body else False)

    # Unknown route returns 404
    status, _ = http_get("/nonexistent")
    check("Unknown route returns 404", status == 404, f"got {status}")


def check_both_backends():
    """Verify both app-01 and app-02 respond through NGINX."""
    print("\n[3] Both backends")
    seen = set()
    for _ in range(20):
        status, body = http_get("/instance")
        if status == 200 and body:
            seen.add(body.get("instance_id"))
    check("app-01 responds", "app-01" in seen, f"seen: {seen}")
    check("app-02 responds", "app-02" in seen, f"seen: {seen}")


def check_network_isolation():
    """Check that NGINX cannot reach postgres/redis (is not on backend network)."""
    print("\n[4] Network isolation")

    # Check NGINX is NOT on backend network
    out, rc = docker("inspect", "nginx", "--format", "{{json .NetworkSettings.Networks}}")
    if rc == 0:
        networks = json.loads(out)
        network_names = list(networks.keys())
        has_backend = any("backend" in n for n in network_names)
        has_frontend = any("frontend" in n for n in network_names)
        check("NGINX is on frontend network", has_frontend, f"networks: {network_names}")
        check("NGINX is NOT on backend network", not has_backend, f"networks: {network_names}")
    else:
        check("Can inspect nginx container", False, "docker inspect failed")

    # Check postgres is only on backend
    out, rc = docker("inspect", "postgres", "--format", "{{json .NetworkSettings.Networks}}")
    if rc == 0:
        networks = json.loads(out)
        network_names = list(networks.keys())
        has_backend = any("backend" in n for n in network_names)
        only_backend = all("backend" in n for n in network_names)
        check("PostgreSQL is on backend only", has_backend and only_backend, f"networks: {network_names}")
    else:
        check("Can inspect postgres container", False, "docker inspect failed")

    # Check redis is only on backend
    out, rc = docker("inspect", "redis", "--format", "{{json .NetworkSettings.Networks}}")
    if rc == 0:
        networks = json.loads(out)
        network_names = list(networks.keys())
        has_backend = any("backend" in n for n in network_names)
        only_backend = all("backend" in n for n in network_names)
        check("Redis is on backend only", has_backend and only_backend, f"networks: {network_names}")
    else:
        check("Can inspect redis container", False, "docker inspect failed")


def check_prohibited_ports():
    """Check that postgres and redis ports are NOT published on the host."""
    print("\n[5] Prohibited host ports")

    for service in ["postgres", "redis"]:
        out, rc = docker("inspect", service, "--format", "{{json .NetworkSettings.Ports}}")
        if rc == 0:
            ports = json.loads(out)
            # Published ports have a non-null binding list
            published = {k: v for k, v in ports.items() if v is not None and len(v) > 0}
            check(f"{service} has no published ports", len(published) == 0, f"published: {published}")
        else:
            check(f"Can inspect {service}", False, "docker inspect failed")


def main():
    print("=" * 60)
    print("  BARQ Environment Validation")
    print("=" * 60)

    if not wait_for_ready():
        print("\nFAILED: Environment not ready within timeout")
        sys.exit(1)

    check_public_access()
    check_all_endpoints()
    check_both_backends()
    check_network_isolation()
    check_prohibited_ports()

    print("\n" + "=" * 60)
    print(f"  Results: {passed} passed, {failed} failed")
    print("=" * 60)

    if failed > 0:
        print("\nVALIDATION FAILED")
        sys.exit(1)
    else:
        print("\nVALIDATION PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
