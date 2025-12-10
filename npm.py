import re
from typing import Optional, Tuple
from urllib.parse import urlparse, unquote
import time
from datetime import datetime, timedelta
import requests


NPM_REGISTRY = {"registry.npmjs.org"}
TARBALL_VER_RE = re.compile(r"-([0-9]+\.[0-9]+\.[0-9][^/]*)\.tgz$")


def _extract_from_registry_tarball(path: str) -> Optional[Tuple[str, str]]:
    if not path.endswith(".tgz"):
        return None
    m = TARBALL_VER_RE.search(path)
    if not m:
        return None
    ver = m.group(1)
    parts = [p for p in path.split("/") if p]
    if len(parts) < 3 or parts[-2] != "-":
        return None
    dash_idx = parts.index("-")
    pkg_parts = parts[:dash_idx]
    if not pkg_parts:
        return None
    pkg = "/".join(unquote(p) for p in pkg_parts)
    return pkg, unquote(ver)


def extract_pkg_and_version(url: str) -> Optional[Tuple[str, str]]:
    u = urlparse(url)
    host = u.hostname
    path = u.path
    if host in NPM_REGISTRY:
        return _extract_from_registry_tarball(path)
    return None


def _get_package_info(pkg: str, registry: str = "https://registry.npmjs.org/") -> dict:
    # Ensure registry ends with / for proper URL construction
    if not registry.endswith("/"):
        registry += "/"
    r = requests.get(f"{registry}{pkg}", timeout=10)
    r.raise_for_status()
    return r.json()


def scan_for_brandnew_packages(
    url: str,
    min_package_age_days: int = 730,
    registry: str = "https://registry.npmjs.org/",
):
    pv = extract_pkg_and_version(url)
    if not pv:
        return
    pkg, ver = pv

    data = _get_package_info(pkg, registry)
    time_map = data.get("time", {})
    package_modified = time_map[ver]

    modified_date = datetime.fromisoformat(package_modified.replace("Z", "+00:00"))
    if datetime.now(modified_date.tzinfo) - modified_date < timedelta(
        days=min_package_age_days
    ):
        raise Exception(
            f"Package {pkg} version {ver} was modified less than {min_package_age_days} days ago."
        )
