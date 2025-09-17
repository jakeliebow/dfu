import re
import time
import subprocess
import os
from pathlib import Path
import requests


def run_npm_install(
    tempdir: str, project_dir: str, proxy_host: str, proxy_port: int, npm_args=None
):
    td = Path(tempdir)
    npmrc = td / "npm_temp.npmrc"
    done = td / "npm_done"

    wait_deadline = time.time() + 120.0
    while not npmrc.exists():
        if time.time() > wait_deadline:
            raise TimeoutError("timed out waiting for npm_temp.npmrc")
        time.sleep(0.1)
    _wait_for_proxy(proxy_host, proxy_port)

    cmd = ["npm", "i", "--userconfig", str(npmrc)]
    if npm_args:
        cmd.extend(npm_args)
    proc = subprocess.Popen(cmd, cwd=project_dir)
    rc = proc.wait()

    try:
        done.write_text(str(rc), encoding="utf-8")
    except Exception:
        pass
    os._exit(rc)


def _wait_for_proxy(proxy_host: str, proxy_port: int):
    ping_path = "/__proxy_ping"

    def _http_ping_via_proxy_self(
        phost: str, pport: int, ping_path: str = "/__proxy_ping", timeout: float = 1.0
    ) -> bool:
        url = f"http://{phost}:{pport}{ping_path}"
        try:
            r = requests.get(url, timeout=timeout)
            return r.status_code == 200 and r.text.strip() == "PONG"
        except requests.RequestException:
            return False

    probe_deadline = time.time() + 120.0
    while time.time() < probe_deadline:
        if _http_ping_via_proxy_self(
            proxy_host, proxy_port, ping_path=ping_path, timeout=1.0
        ):
            break
        time.sleep(0.1)
    else:
        raise TimeoutError(
            f"Timed out waiting for PONG from proxy {proxy_host}:{proxy_port}"
        )
