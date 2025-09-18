import re
import time
import subprocess
import sys
import os
import signal
from pathlib import Path
import requests
from proxy import detect_yarn_version


def run_package_manager(
    tempdir: str,
    project_dir: str,
    proxy_host: str,
    proxy_port: int,
    package_manager: str,
    pm_args=None,
):
    td = Path(tempdir)

    if package_manager == "npm":
        config_file = td / f"{package_manager}_temp.{package_manager}rc"
    elif package_manager == "yarn":
        yarn_version = detect_yarn_version()
        if yarn_version is None or yarn_version >= 2:
            # Yarn 2+ format (or fallback if detection fails)
            config_file = td / "yarn_temp.yarnrc.yml"
        else:
            # Yarn 1.x format
            config_file = td / "yarn_temp.yarnrc"
    else:
        raise ValueError(f"Unsupported package manager: {package_manager}")
    done = td / "pm_done"

    wait_deadline = time.time() + 120.0
    while not config_file.exists():
        if time.time() > wait_deadline:
            print(f"Timed out waiting for {config_file.name}", flush=True)
            try:
                done.write_text("1", encoding="utf-8")
            except Exception:
                pass
            os._exit(1)
        time.sleep(0.1)
    try:
        _wait_for_proxy(proxy_host, proxy_port)
    except Exception as e:
        print(f"Error waiting for proxy: {e}", flush=True)
        print("Error logged during startup, exiting...", flush=True)
        try:
            done.write_text("1", encoding="utf-8")
        except Exception:
            pass
        os._exit(1)

    if package_manager == "npm":
        cmd = ["npm", "--userconfig", str(config_file)]
        if pm_args:
            cmd.extend(pm_args)
    elif package_manager == "yarn":
        print(
            "⚠️  WARNING: Yarn proxy configuration uses HTTP (not HTTPS) due to yarn limitations.",
            file=sys.stderr,
        )
        print("   This may result in less secure package downloads.", file=sys.stderr)

        yarn_version = detect_yarn_version()
        if yarn_version is None or yarn_version >= 2:
            cmd = ["yarn", "--rc-filename", str(config_file)]
        else:
            cmd = ["yarn", "--use-yarnrc", str(config_file)]

        if pm_args:
            cmd.extend(pm_args)

    # Set up environment with proxy settings for yarn
    env = os.environ.copy()
    env["HTTP_PROXY"] = f"http://{proxy_host}:{proxy_port}"
    env["HTTPS_PROXY"] = f"http://{proxy_host}:{proxy_port}"
    env["http_proxy"] = f"http://{proxy_host}:{proxy_port}"
    env["https_proxy"] = f"http://{proxy_host}:{proxy_port}"

    # Global reference to subprocess so signal handler can access it
    global current_proc
    current_proc = None

    def cleanup_handler(signum, frame):
        if current_proc and current_proc.poll() is None:
            try:
                current_proc.kill()
                current_proc.wait(timeout=2)
            except Exception:
                pass
        os._exit(1)

    # Set up signal handlers
    signal.signal(signal.SIGTERM, cleanup_handler)
    signal.signal(signal.SIGINT, cleanup_handler)

    try:
        proc = subprocess.Popen(cmd, cwd=project_dir, env=env, preexec_fn=os.setsid)
        current_proc = proc
        rc = proc.wait()
    except Exception as e:
        print(f"Error running package manager: {e}", flush=True)
        rc = 1

    try:
        done.write_text(str(rc), encoding="utf-8")
    except Exception:
        pass
    os._exit(rc)


def _wait_for_proxy(proxy_host: str, proxy_port: int):
    ping_path = "/__proxy_ping"
    print(f"Waiting for proxy at {proxy_host}:{proxy_port}", flush=True)

    def _http_ping_via_proxy_self(
        phost: str, pport: int, ping_path: str = "/__proxy_ping", timeout: float = 1.0
    ) -> bool:
        url = f"http://{phost}:{pport}{ping_path}"
        try:
            r = requests.get(url, timeout=timeout)
            result = r.status_code == 200 and r.text.strip() == "PONG"
            if result:
                print(
                    f"Successfully pinged proxy: {r.status_code} {r.text.strip()}",
                    flush=True,
                )
            else:
                print(
                    f"Ping failed: status={r.status_code}, text='{r.text.strip()}'",
                    flush=True,
                )
            return result
        except requests.RequestException as e:
            print(f"Connection error: {e}", flush=True)
            return False

    probe_deadline = time.time() + 120.0
    attempts = 0
    while time.time() < probe_deadline:
        attempts += 1
        if attempts % 50 == 0:  # Log every 5 seconds
            print(f"Still waiting for proxy... attempt {attempts}", flush=True)
        if _http_ping_via_proxy_self(
            proxy_host, proxy_port, ping_path=ping_path, timeout=1.0
        ):
            print("Proxy is ready!", flush=True)
            break
        time.sleep(0.1)
    else:
        print(f"Timed out after {attempts} attempts", flush=True)
        raise TimeoutError(
            f"Timed out waiting for PONG from proxy {proxy_host}:{proxy_port}"
        )
