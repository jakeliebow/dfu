import asyncio
from pathlib import Path
from mitmproxy import options, http
from mitmproxy.tools.dump import DumpMaster
from certificate import make_ca, _pem_for_cert, _pem_for_key
from npm import scan_for_brandnew_packages


class RequestHook:
    def __init__(self, min_package_age: int):
        self.min_package_age = min_package_age

    def request(self, flow: http.HTTPFlow) -> None:
        PING_PATH = "/__proxy_ping"
        if flow.request.path.startswith(PING_PATH):
            flow.response = http.Response.make(
                200, b"PONG", {"Content-Type": "text/plain"}
            )
            return

        # Scan package downloads for age validation
        # This works with the normal proxy flow where npm hits registry.npmjs.org through our proxy
        if flow.request.host == "registry.npmjs.org" and flow.request.url.endswith(
            ".tgz"
        ):
            scan_for_brandnew_packages(flow.request.url, self.min_package_age)

        return


def run_proxy(tempdir: str, host: str, port: int, min_package_age: int):
    td = Path(tempdir)
    confdir = td / "confdir"
    confdir.mkdir(exist_ok=True)

    ca_key, ca_cert = make_ca()
    combined = confdir / "mitmproxy-ca.pem"
    cert_only = confdir / "mitmproxy-ca-cert.pem"

    combined.write_bytes(_pem_for_cert(ca_cert) + b"\n" + _pem_for_key(ca_key))
    cert_only.write_bytes(_pem_for_cert(ca_cert))

    npmrc_path = td / "npm_temp.npmrc"
    proxy_url = f"https://{host}:{port}"
    npmrc_lines = [
        "registry=https://registry.npmjs.org/",
        f"proxy={proxy_url}",
        f"https-proxy={proxy_url}",
        f"strict-ssl=true",
        f"cafile={str(cert_only.resolve())}",
        "noproxy=",
    ]
    npmrc_path.write_text("\n".join(npmrc_lines) + "\n", encoding="utf-8")
    ready_file = td / "mitmproxy_ready"
    ready_file.touch()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    asyncio.get_running_loop = lambda: loop

    opts = options.Options(listen_host=host, listen_port=port, confdir=str(confdir))
    m = DumpMaster(opts, with_termlog=False, with_dumper=False)
    m.addons.add(RequestHook(min_package_age))
    asyncio.run(m.run())
