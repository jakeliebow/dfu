import argparse
import tempfile
import sys
import os
from pathlib import Path
from multiprocessing import Process
from proxy import run_proxy
from npm_runner import run_npm_install


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--project",
        "-C",
        default=os.getcwd(),
        help="Path to project directory to run `npm i` in (defaults to current directory)",
    )
    p.add_argument("--port", type=int, default=8080, help="Proxy port")
    p.add_argument("--host", default="127.0.0.1", help="Proxy host address")
    p.add_argument(
        "--min-package-age",
        type=int,
        default=14,
        help="Minimum package age in days (default: 14 days)",
    )
    args, unknown_args = p.parse_known_args()
    npm_args = []
    i = 0
    while i < len(unknown_args):
        if unknown_args[i] == "--userconfig":
            raise Exception("dfu does not support custom --userconfig arguments")
        else:
            npm_args.append(unknown_args[i])
            i += 1

    project_dir = str(Path(args.project).resolve())
    if not Path(project_dir).exists():
        print("error: project dir not found", file=sys.stderr)
        sys.exit(2)
    with tempfile.TemporaryDirectory(prefix="mitm_orch_") as td:
        proxy_proc = Process(
            target=run_proxy,
            args=(td, args.host, args.port, args.min_package_age),
            daemon=True,
        )
        npm_proc = Process(
            target=run_npm_install,
            args=(
                td,
                project_dir,
                args.host,
                args.port,
                npm_args if npm_args else None,
            ),
            daemon=False,
        )

        proxy_proc.start()
        npm_proc.start()
        npm_proc.join()
        rc = None
        if npm_proc.exitcode is not None and npm_proc.exitcode != 0:
            rc = npm_proc.exitcode
        else:
            try:
                done_path = Path(td) / "npm_done"
                if done_path.exists():
                    rc = int(done_path.read_text().strip() or 0)
            except Exception:
                rc = 0
        if proxy_proc.is_alive():
            proxy_proc.terminate()
            proxy_proc.join(timeout=5)
        sys.exit(rc or 0)


if __name__ == "__main__":
    main()
