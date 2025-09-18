import argparse
import tempfile
import sys
import os
import time
from pathlib import Path
from multiprocessing import Process
from proxy import run_proxy
from npm_runner import run_package_manager


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--project",
        "-C",
        default=os.getcwd(),
        help="Path to project directory to run `npm i` in (defaults to current directory)",
    )
    p.add_argument("--port", type=int, default=8080, help="Proxy port")
    p.add_argument("--host", default="localhost", help="Proxy host address")
    p.add_argument(
        "--min-package-age-days",
        type=int,
        default=14,
        help="Minimum package age in days (default: 14 days)",
    )
    p.add_argument(
        "--registry",
        default="https://registry.npmjs.org/",
        help="Package registry URL (default: https://registry.npmjs.org/)",
    )
    p.add_argument(
        "--unsafe-http",
        action="store_true",
        help="Allow unsafe HTTP connections (required for yarn)",
    )
    args, unknown_args = p.parse_known_args()

    # Parse package manager and command from unknown args
    if not unknown_args:
        print(
            "error: please specify package manager and command (e.g., 'dfu npm i package-name')",
            file=sys.stderr,
        )
        sys.exit(1)

    package_manager = unknown_args[0]
    if package_manager not in ["npm", "yarn"]:
        print(
            f"error: unsupported package manager '{package_manager}'. Supported: npm, yarn",
            file=sys.stderr,
        )
        sys.exit(1)

    # Check if yarn is being used without --unsafe-http flag
    if package_manager == "yarn" and not args.unsafe_http:
        print(
            "error: yarn can only be run with the --unsafe-http flag",
            file=sys.stderr,
        )
        sys.exit(1)

    pm_args = []
    i = 1
    while i < len(unknown_args):
        if unknown_args[i] == "--userconfig":
            raise Exception("dfu does not support custom --userconfig arguments")
        else:
            pm_args.append(unknown_args[i])
            i += 1

    project_dir = str(Path(args.project).resolve())
    if not Path(project_dir).exists():
        print("error: project dir not found", file=sys.stderr)
        sys.exit(2)
    with tempfile.TemporaryDirectory(prefix="mitm_orch_") as td:
        proxy_proc = Process(
            target=run_proxy,
            args=(td, args.host, args.port, args.min_package_age, args.registry),
            daemon=True,
        )
        pm_proc = Process(
            target=run_package_manager,
            args=(
                td,
                project_dir,
                args.host,
                args.port,
                package_manager,
                pm_args if pm_args else None,
            ),
            daemon=False,
        )

        proxy_proc.start()
        pm_proc.start()

        # Monitor both processes and error signals
        rc = None
        proxy_error_file = Path(td) / "proxy_error"
        pm_done_file = Path(td) / "pm_done"

        try:
            while True:
                # Check if proxy process has died
                if not proxy_proc.is_alive():
                    print(
                        "Proxy process has died, shutting down package manager",
                        flush=True,
                    )
                    if pm_proc.is_alive():
                        pm_proc.terminate()
                        pm_proc.join(timeout=5)
                    rc = 1
                    break

                # Check for proxy error signal
                if proxy_error_file.exists():
                    error_msg = proxy_error_file.read_text(encoding="utf-8").strip()
                    print(f"Proxy error detected: {error_msg}", flush=True)
                    if pm_proc.is_alive():
                        # Kill the package manager process quietly
                        pm_proc.terminate()
                        pm_proc.join(timeout=2)
                    rc = 1
                    break

                # Check if package manager process has finished
                if not pm_proc.is_alive():
                    print("Package manager process has finished", flush=True)
                    if pm_proc.exitcode is not None and pm_proc.exitcode != 0:
                        rc = pm_proc.exitcode
                    else:
                        try:
                            if pm_done_file.exists():
                                rc = int(pm_done_file.read_text().strip() or 0)
                        except Exception:
                            rc = 0
                    break

                time.sleep(0.1)

        finally:
            # Ensure both processes are terminated
            if proxy_proc.is_alive():
                proxy_proc.terminate()
                proxy_proc.join(timeout=5)
            if pm_proc.is_alive():
                pm_proc.terminate()
                pm_proc.join(timeout=5)

        sys.exit(rc or 0)


if __name__ == "__main__":
    main()
