#!/usr/bin/env python3
"""Exercise the actual Docker composition with synthetic, provider-disabled data.

Run after `docker build -t stride-ci .`: python deploy/container_smoke.py stride-ci
No production credentials, databases or remote providers are used.
"""
import argparse
import http.cookiejar
import http.client
import json
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from uuid import uuid4


def wait_for_readiness(root, attempts=90):
    """Published Docker ports may reset connections before Node starts listening."""
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(root + "/healthz", timeout=3) as response:
                if response.status == 200:
                    return
        except (OSError, http.client.HTTPException):
            # URLError/HTTPError, timeouts, resets and incomplete startup responses
            # are retryable only within this bounded startup window.
            pass
        time.sleep(1)
    raise RuntimeError("Container never became ready")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image")
    args = parser.parse_args()
    name = "stride-smoke-" + uuid4().hex[:10]
    password = "synthetic-ci-password"
    with tempfile.TemporaryDirectory(prefix="stride-container-data-") as temp:
        mount = f"{Path(temp).resolve()}:/var/data"
        common = ["-v", mount, "-e", "DATABASE_URL=sqlite:////var/data/stride.db",
                  "-e", "GARMIN_POLL_MINUTES=0", "-e", "OPENAI_AUTO_REVIEWS=false",
                  "-e", "OPENAI_API_KEY=", "-e", "ANTHROPIC_API_KEY=", "-e", "ATHLETE_PROFILE_DOC=",
                  "-e", "GARMIN_API_KEY=", "-e", "TZ=America/Los_Angeles"]

        def docker(*values, **kwargs):
            return subprocess.run(["docker", *values], check=True, text=True, capture_output=True, **kwargs).stdout

        def start():
            docker("run", "-d", "--name", name, "-p", "127.0.0.1::10000", *common,
                   "-e", "RENDER=true", "-e", f"STRIDE_PASSWORD={password}", args.image)
            port = docker("port", name, "10000/tcp").strip().split(":")[-1]
            root = f"http://127.0.0.1:{port}"
            wait_for_readiness(root)
            return root

        def inspect(root):
            try:
                urllib.request.urlopen(root + "/api/plans/1/current", timeout=5)
                raise AssertionError("API exposed without authentication")
            except urllib.error.HTTPError as exc:
                assert exc.code == 401, exc.code
            opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            form = urllib.parse.urlencode({"password": password, "next": "/plan"}).encode()
            with opener.open(root + "/auth", data=form, timeout=10) as response:
                assert response.status == 200
            with opener.open(root + "/api/plans/1/current", timeout=10) as response:
                plan = json.load(response)
            assert plan["id"] and plan["weeks"]
            return plan["id"]

        try:
            docker("run", "--rm", *common, "--entrypoint", "python", args.image, "/app/demo/seed.py",
                   "--scenario", "sub17-5k", "--database", "/var/data/stride.db")
            plan_id = inspect(start())
            docker("stop", name)
            docker("rm", name)
            assert inspect(start()) == plan_id, "Approved plan did not survive a fresh container"
            # Restore a pre-start snapshot to a NEW disposable file using the production tool.
            script = ("from pathlib import Path; from app.services.backups import restore_new; "
                      "backups=sorted(Path('/var/data/backups').glob('stride-*.sqlite3')); "
                      "assert backups; counts=restore_new(backups[-1],Path('/var/data/restored.db')); "
                      "assert counts['activities']>0; print('SQLite restore verified')")
            print(docker("exec", "-w", "/app/backend", name, "python", "-c", script).strip())
            # An actually dead backend must cause the supervisor to terminate the container.
            docker("exec", name, "sh", "-c", "kill $(cat /tmp/stride-backend.pid)")
            for _ in range(20):
                state = json.loads(docker("inspect", name))[0]["State"]
                if not state["Running"]:
                    assert state["ExitCode"] != 0
                    break
                time.sleep(1)
            else:
                raise AssertionError("Supervisor left a frontend running after backend death")
            print("Container auth, health, persistent restart, backup restore and supervision passed.")
        finally:
            subprocess.run(["docker", "logs", name], check=False)
            subprocess.run(["docker", "rm", "-f", name], check=False, capture_output=True)
            # The volume contains ONLY this test's generated synthetic fixtures.
            subprocess.run(["docker", "run", "--rm", "-v", mount, "--entrypoint", "sh", args.image,
                            "-c", "chmod -R a+rwX /var/data"], check=False, capture_output=True)


if __name__ == "__main__":
    main()
