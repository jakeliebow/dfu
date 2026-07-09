import asyncio
import subprocess
from pathlib import Path
from aiohttp import web, ClientSession, ClientTimeout
from npm import scan_for_brandnew_packages


def detect_yarn_version():
    """Detect yarn version and return major version number or None if yarn not found"""
    try:
        result = subprocess.run(
            ["yarn", "--version"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            version_str = result.stdout.strip()
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


HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "content-encoding",
    "content-length",
}


def _make_handler(min_package_age: int, registry: str, local_url: str):
    async def handler(request: web.Request) -> web.StreamResponse:
        path = request.match_info["path"]
        if path == "__proxy_ping":
            return web.Response(text="PONG")

        upstream = registry + path
        if request.query_string:
            upstream += "?" + request.query_string

        if upstream.endswith(".tgz"):
            try:
                blocked = scan_for_brandnew_packages(upstream, min_package_age, registry)
                if blocked:
                    return web.Response(
                        status=403,
                        text=f"Package blocked: {upstream} is less than {min_package_age} days old",
                        content_type="text/plain",
                    )
            except Exception as e:
                print(f"Error scanning package: {e}", flush=True)
                return web.Response(
                    status=500,
                    text=f"Error scanning package: {e}",
                    content_type="text/plain",
                )

        req_headers = {
            k: v for k, v in request.headers.items() if k.lower() != "host"
        }
        body = await request.read() if request.can_read_body else None

        timeout = ClientTimeout(total=60)
        async with ClientSession(timeout=timeout, auto_decompress=True) as session:
            async with session.request(
                request.method,
                upstream,
                headers=req_headers,
                data=body,
                allow_redirects=False,
            ) as upstream_resp:
                resp_body = await upstream_resp.read()
                content_type = upstream_resp.headers.get("Content-Type", "")
                if "application/json" in content_type and request.method.upper() == "GET":
                    resp_body = resp_body.replace(
                        registry.encode("utf-8"), local_url.encode("utf-8")
                    )
                resp_headers = {
                    k: v
                    for k, v in upstream_resp.headers.items()
                    if k.lower() not in HOP_BY_HOP
                }
                return web.Response(
                    status=upstream_resp.status,
                    body=resp_body,
                    headers=resp_headers,
                )

    return handler


def run_proxy(
    host: str,
    port: int,
    min_package_age: int,
    root_path: str,
    registry: str = "https://registry.npmjs.org/",
):
    if not registry.endswith("/"):
        registry += "/"

    base_dir = Path.cwd() / "proxy_files"
    base_dir.mkdir(parents=True, exist_ok=True)
    print(f"Starting proxy setup in {base_dir}", flush=True)

    local_url = f"http://{host}:{port}/"

    npmrc_path = base_dir / "dfu.npmrc"
    npmrc_lines = [
        f"registry={local_url}",
        "fetch-retries=0",
        "prefer-online=true",
        "fetch-retry-mintimeout=0",
        "fetch-retry-maxtimeout=0",
        "maxsockets=1",
    ]
    npmrc_path.write_text("\n".join(npmrc_lines) + "\n", encoding="utf-8")
    print(f"NPM config path: {npmrc_path.resolve()}", flush=True)

    yarn_version = detect_yarn_version()
    print(f"Detected yarn version: {yarn_version}", flush=True)

    if yarn_version is None or yarn_version >= 2:
        yarnrc_yml_path = base_dir / "dfu.yarnrc.yml"
        yarnrc_yml_content = (
            f'npmRegistryServer: "{local_url}"\n'
            f"unsafeHttpWhitelist:\n"
            f'  - "{host}"\n'
            f"networkTimeout: 30000\n"
            f"networkConcurrency: 1\n"
            f"httpRetryCount: 0\n"
        )
        yarnrc_yml_path.write_text(yarnrc_yml_content, encoding="utf-8")
        print(f"Yarn config path: {yarnrc_yml_path.resolve()}", flush=True)
    else:
        yarnrc_path = base_dir / "dfu.yarnrc"
        yarnrc_content = (
            f'registry "{local_url}"\n'
            f"network-timeout 1000\n"
            f"network-concurrency 1\n"
            f"network-retry-count 0\n"
        )
        yarnrc_path.write_text(yarnrc_content, encoding="utf-8")
        print(f"Yarn config path: {yarnrc_path.resolve()}", flush=True)

    async def _serve():
        app = web.Application()
        handler = _make_handler(min_package_age, registry, local_url)
        app.router.add_route("*", "/{path:.*}", handler)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        await site.start()
        print(f"Server listening on http://{host}:{port}", flush=True)
        while True:
            await asyncio.sleep(3600)

    try:
        asyncio.run(_serve())
    except Exception as e:
        print(f"Error starting HTTP server: {e}", flush=True)
