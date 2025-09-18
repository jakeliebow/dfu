import asyncio
import subprocess
from pathlib import Path
from mitmproxy import options, http
from mitmproxy.tools.dump import DumpMaster
from certificate import make_ca, _pem_for_cert, _pem_for_key
from npm import scan_for_brandnew_packages


def detect_yarn_version():
    """Detect yarn version and return major version number or None if yarn not found"""
    try:
        result = subprocess.run(
            ["yarn", "--version"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            version_str = result.stdout.strip()
            # Parse version like "1.22.22" or "3.6.4"
            major_version = int(version_str.split(".")[0])
            return major_version
    except (
        subprocess.TimeoutExpired,
        subprocess.SubprocessError,
        ValueError,
        FileNotFoundError,
    ):
        pass
    return None


class RequestHook:
    def __init__(self, min_package_age: int, error_file: Path, registry: str):
        self.min_package_age = min_package_age
        self.error_file = error_file
        self.registry = registry

    def request(self, flow: http.HTTPFlow) -> None:
        PING_PATH = "/__proxy_ping"
        if flow.request.path.startswith(PING_PATH):
            flow.response = http.Response.make(
                200, b"PONG", {"Content-Type": "text/plain"}
            )
            return
        if flow.request.url.endswith(".tgz"):
            try:
                scan_for_brandnew_packages(
                    flow.request.url, self.min_package_age, self.registry
                )
            except Exception as e:
                error_message = f"""
ERROR: DFU has blocked {flow.request.url} 
PIN/DOWNGRADE PACKAGE VERSIONS OR A PACKAGE MANAGER DIRECTLY TO INSTALL
                """
                flow.response = http.Response.make(
                    403,
                    f"Package blocked: {str(e)}".encode(),
                    {"Content-Type": "text/plain"},
                )
                # Signal fatal error to main process
                try:
                    self.error_file.write_text(
                        f"Package blocked: {str(e)}", encoding="utf-8"
                    )
                except Exception:
                    pass
                raise Exception(error_message)

        return


def run_proxy(
    tempdir: str,
    host: str,
    port: int,
    min_package_age: int,
    registry: str = "https://registry.npmjs.org/",
):
    print(f"Starting proxy setup in {tempdir}", flush=True)
    td = Path(tempdir)
    confdir = td / "confdir"
    confdir.mkdir(exist_ok=True)
    print("Created confdir", flush=True)

    # Error signaling file
    error_file = td / "proxy_error"

    ca_key, ca_cert = make_ca()
    print("Generated CA certificates", flush=True)
    combined = confdir / "mitmproxy-ca.pem"
    cert_only = confdir / "mitmproxy-ca-cert.pem"

    combined.write_bytes(_pem_for_cert(ca_cert) + b"\n" + _pem_for_key(ca_key))
    cert_only.write_bytes(_pem_for_cert(ca_cert))
    print("Wrote certificate files", flush=True)

    npmrc_path = td / "npm_temp.npmrc"
    proxy_url = f"https://{host}:{port}"
    npmrc_lines = [
        f"registry={registry}",
        f"proxy={proxy_url}",
        f"https-proxy={proxy_url}",
        f"strict-ssl=true",
        f"cafile={str(cert_only.resolve())}",
        "noproxy=",
        "fetch-retries=0",
        "prefer-online=true",
        "fetch-retry-mintimeout=0",
        "fetch-retry-maxtimeout=0",
        "maxsockets=1",
    ]
    npmrc_path.write_text("\n".join(npmrc_lines) + "\n", encoding="utf-8")

    # Create yarn config based on detected version
    # Note: Using HTTP proxy instead of HTTPS due to yarn proxy limitations
    yarn_version = detect_yarn_version()
    http_proxy_url = f"http://{host}:{port}"
    print(f"Detected yarn version: {yarn_version}", flush=True)

    if yarn_version is None or yarn_version >= 2:
        # Yarn 2+ format (or fallback if detection fails)
        yarnrc_yml_path = td / "yarn_temp.yarnrc.yml"
        yarnrc_yml_content = f"""httpProxy: "{http_proxy_url}"
httpsProxy: "{http_proxy_url}"
strictSsl: true
caFilePath: "{str(cert_only.resolve())}"
networkTimeout: 30000
networkConcurrency: 1
httpRetryCount: 0
"""
        yarnrc_yml_path.write_text(yarnrc_yml_content, encoding="utf-8")
        print(f"Created Yarn 2+ config: {yarnrc_yml_path}", flush=True)
    else:
        # Yarn 1.x format
        yarnrc_path = td / "yarn_temp.yarnrc"
        yarnrc_content = f"""proxy "{http_proxy_url}"
https-proxy "{http_proxy_url}"
strict-ssl false
registry "{registry}"
network-timeout 1000
network-concurrency 1
network-retry-count 0
"""
        yarnrc_path.write_text(yarnrc_content, encoding="utf-8")
        print(f"Created Yarn 1.x config: {yarnrc_path}", flush=True)
    ready_file = td / "mitmproxy_ready"
    ready_file.touch()

    print("Setting up event loop", flush=True)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    asyncio.get_running_loop = lambda: loop

    try:
        print(f"Creating mitmproxy options: host={host}, port={port}", flush=True)
        opts = options.Options(listen_host=host, listen_port=port, confdir=str(confdir))
        print("Creating DumpMaster", flush=True)
        m = DumpMaster(opts, with_termlog=False, with_dumper=False)
        print("Adding request hook", flush=True)
        m.addons.add(RequestHook(min_package_age, error_file, registry))
        print("Starting mitmproxy", flush=True)
        asyncio.run(m.run())
    except Exception as e:
        print(f"Error starting mitmproxy: {e}", flush=True)
        import traceback

        traceback.print_exc()
        # Signal fatal error to main process
        try:
            error_file.write_text(f"Proxy startup error: {str(e)}", encoding="utf-8")
        except Exception:
            pass
        raise
