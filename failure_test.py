#!/usr/bin/env python3
"""Failure test: stop one backend, measure traffic/errors, restore it and verify recovery."""
import json
import subprocess
import sys
import time
import urllib.request
import urllib.error

BASE_URL = "http://127.0.0.1:8080"
TIMEOUT = 5
REQUESTS_PER_PHASE = 20


def http_get(path):
    """Make an HTTP GET request, return (status_code, body_dict, instance_id) or (None, None, None)."""
    try:
        req = urllib.request.Request(f"{BASE_URL}{path}")
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = json.loads(resp.read().decode())
            instance = resp.headers.get("X-Instance-ID", "unknown")
            return resp.status, body, instance
    except urllib.error.HTTPError as e:
        return e.code, None, None
    except Exception:
        return None, None, None


def docker(*args):
    """Run a docker command."""
    result = subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        print(f"    Docker error: {result.stderr.strip()}")
    return result.returncode


def wait_for_healthy(container, max_wait=60):
    """Wait for a container to become healthy."""
    start = time.time()
    while time.time() - start < max_wait:
        result = subprocess.run(
            ["docker", "inspect", container, "--format", "{{.State.Health.Status}}"],
            capture_output=True, text=True, timeout=10
        )
        status = result.stdout.strip()
        if status == "healthy":
            return True
        time.sleep(2)
    return False


def send_traffic(label, num_requests):
    """Send requests and measure success/failure/instances seen."""
    print(f"\n    Sending {num_requests} requests ({label})...")
    successes = 0
    failures = 0
    errors = 0
    instances = {}

    for _ in range(num_requests):
        status, body, instance = http_get("/instance")
        if status == 200:
            successes += 1
            instances[instance] = instances.get(instance, 0) + 1
        elif status is not None:
            failures += 1
        else:
            errors += 1
        time.sleep(0.1)

    total = successes + failures + errors
    print(f"    Results: {successes}/{total} success, {failures} HTTP errors, {errors} connection errors")
    print(f"    Instances seen: {instances}")
    return successes, failures, errors, instances


def main():
    print("=" * 60)
    print("  BARQ Failure Test")
    print("=" * 60)

    # Phase 1: Verify both backends are healthy
    print("\n[1] Pre-check: verifying both backends respond")
    successes, failures, errors, instances = send_traffic("pre-check", REQUESTS_PER_PHASE)
    if "app-01" not in instances or "app-02" not in instances:
        print("\nFAILED: Both backends must be responding before failure test")
        print(f"    Instances seen: {list(instances.keys())}")
        sys.exit(1)
    print("    PASS: Both app-01 and app-02 are responding")

    # Phase 2: Stop one backend
    target = "app-02"
    print(f"\n[2] Stopping {target}...")
    rc = docker("stop", target)
    if rc != 0:
        print(f"FAILED: Could not stop {target}")
        sys.exit(1)
    print(f"    {target} stopped")
    time.sleep(2)

    # Phase 3: Measure traffic during failure
    print(f"\n[3] Measuring traffic with {target} down")
    successes, failures, errors, instances = send_traffic("during failure", REQUESTS_PER_PHASE)

    check_availability = successes > 0
    check_single_backend = len(instances) == 1 and "app-01" in instances
    print(f"\n    Service still available: {'PASS' if check_availability else 'FAIL'}")
    print(f"    Only app-01 serving:     {'PASS' if check_single_backend else 'FAIL'}")

    if not check_availability:
        print("\nWARNING: Service was unavailable during failure — restoring and exiting")
        docker("start", target)
        sys.exit(1)

    # Phase 4: Restore the stopped backend
    print(f"\n[4] Restoring {target}...")
    rc = docker("start", target)
    if rc != 0:
        print(f"FAILED: Could not start {target}")
        sys.exit(1)

    print(f"    Waiting for {target} to become healthy...")
    if not wait_for_healthy(target):
        print(f"FAILED: {target} did not become healthy within timeout")
        sys.exit(1)
    print(f"    {target} is healthy")

    # Phase 5: Verify recovery — the restored backend serves requests
    print(f"\n[5] Verifying {target} serves requests after recovery")
    time.sleep(3)  # Give NGINX time to detect the recovered backend
    successes, failures, errors, instances = send_traffic("after recovery", REQUESTS_PER_PHASE)

    check_both = "app-01" in instances and "app-02" in instances
    check_recovered = target.replace("app-0", "app-0") in instances
    print(f"\n    Both backends responding: {'PASS' if check_both else 'FAIL'}")
    print(f"    Recovered {target} serves: {'PASS' if check_recovered else 'FAIL'}")

    # Summary
    print("\n" + "=" * 60)
    all_pass = check_availability and check_single_backend and check_both and check_recovered
    if all_pass:
        print("  FAILURE TEST PASSED")
        print("=" * 60)
        sys.exit(0)
    else:
        print("  FAILURE TEST FAILED")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
