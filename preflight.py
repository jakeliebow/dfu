import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock

import requests


def generate_lockfile(package_json_path: Path, registry: str) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        shutil.copy(package_json_path, tmp_path / "package.json")
        result = subprocess.run(
            [
                "npm",
                "install",
                "--package-lock-only",
                "--no-audit",
                "--no-fund",
                f"--registry={registry}",
            ],
            cwd=tmp_path,
            capture_output=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"npm install failed for {package_json_path}:\n"
                + result.stderr.decode("utf-8", errors="replace")
            )
        return json.loads((tmp_path / "package-lock.json").read_text())


def collect_resolved_packages(lockfile: dict) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for path, info in lockfile.get("packages", {}).items():
        if not path:
            continue
        version = info.get("version")
        if not version:
            continue
        if info.get("link"):
            continue
        resolved = info.get("resolved") or ""
        if resolved.startswith(("file:", "link:")):
            continue
        name = info.get("name") or path.split("node_modules/")[-1]
        key = (name, version)
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


_info_cache: dict[str, dict] = {}
_info_lock = Lock()


def fetch_package_info(pkg: str, registry: str) -> dict:
    with _info_lock:
        cached = _info_cache.get(pkg)
    if cached is not None:
        return cached
    r = requests.get(f"{registry.rstrip('/')}/{pkg}", timeout=15)
    r.raise_for_status()
    data = r.json()
    with _info_lock:
        _info_cache[pkg] = data
    return data


def parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


_PRERELEASE = re.compile(r"[-+]")


def latest_safe_override(
    pkg: str, registry: str, threshold: timedelta, now: datetime
) -> tuple[str, datetime] | None:
    info = fetch_package_info(pkg, registry)
    time_map = info.get("time", {})
    candidates: list[tuple[datetime, str]] = []
    for ver, ts in time_map.items():
        if ver in ("created", "modified"):
            continue
        if _PRERELEASE.search(ver):
            continue
        try:
            published = parse_iso(ts)
        except Exception:
            continue
        if now - published >= threshold:
            candidates.append((published, ver))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    pub, ver = candidates[0]
    return ver, pub


def preflight_one(
    package_json: Path, threshold_days: int, registry: str, workers: int
) -> dict:
    lockfile = generate_lockfile(package_json, registry)
    targets = collect_resolved_packages(lockfile)
    now = datetime.now(timezone.utc)
    threshold = timedelta(days=threshold_days)

    def check(item: tuple[str, str]):
        name, ver = item
        try:
            info = fetch_package_info(name, registry)
            pub = parse_iso(info["time"][ver])
        except Exception as e:
            return ("error", name, ver, str(e))
        if now - pub < threshold:
            return ("blocked", name, ver, pub)
        return None

    blocked: list[tuple[str, str, datetime]] = []
    errors: list[tuple[str, str, str]] = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for r in ex.map(check, targets):
            if r is None:
                continue
            if r[0] == "blocked":
                blocked.append((r[1], r[2], r[3]))
            else:
                errors.append((r[1], r[2], r[3]))

    overrides: dict[str, dict] = {}
    for name, ver, _pub in blocked:
        rec = latest_safe_override(name, registry, threshold, now)
        if rec is None:
            overrides[name] = {
                "blocked_version": ver,
                "suggested": None,
                "suggested_published": None,
            }
        else:
            overrides[name] = {
                "blocked_version": ver,
                "suggested": rec[0],
                "suggested_published": rec[1],
            }

    return {
        "package_json": str(package_json),
        "total": len(targets),
        "blocked": blocked,
        "errors": errors,
        "overrides": overrides,
    }


def print_report(reports: list[dict], threshold_days: int) -> int:
    now = datetime.now(timezone.utc)
    bar = "=" * 80
    print(bar, flush=True)
    print("DFU PREFLIGHT REPORT", flush=True)
    print(bar, flush=True)
    print(
        f"Threshold: {threshold_days} day(s) -- packages younger than this will be rejected by DFU",
        flush=True,
    )
    print(flush=True)

    aggregate: dict[str, dict[str, str]] = {}
    total_blocked = 0
    total_errors = 0

    for r in reports:
        print(f"[{r['package_json']}]", flush=True)
        print(f"  Resolved tree size: {r['total']} package(s)", flush=True)
        if not r["blocked"] and not r["errors"]:
            print("  PASS -- no blocked packages.", flush=True)
            print(flush=True)
            continue
        if r["errors"]:
            print(f"  {len(r['errors'])} resolution error(s):", flush=True)
            for name, ver, msg in r["errors"]:
                print(f"    ! {name}@{ver}: {msg}", flush=True)
        if r["blocked"]:
            print(f"  {len(r['blocked'])} blocked package(s):", flush=True)
            for name, ver, pub in sorted(
                r["blocked"], key=lambda x: x[2], reverse=True
            ):
                age_h = (now - pub).total_seconds() / 3600
                rec = r["overrides"].get(name, {})
                suggested = rec.get("suggested")
                print(f"    - {name}@{ver}", flush=True)
                print(
                    f"        published: {pub.isoformat()}  ({age_h:.1f}h ago)",
                    flush=True,
                )
                if suggested:
                    sp = rec["suggested_published"]
                    print(
                        f'        suggested override: "{name}": "{suggested}"  (published {sp.isoformat()})',
                        flush=True,
                    )
                    aggregate.setdefault(r["package_json"], {})[name] = suggested
                else:
                    print(
                        f"        suggested override: NONE -- no stable version older than {threshold_days} day(s) exists",
                        flush=True,
                    )
        total_blocked += len(r["blocked"])
        total_errors += len(r["errors"])
        print(flush=True)

    print(bar, flush=True)
    print("SUMMARY", flush=True)
    print(bar, flush=True)
    print(f"Total blocked packages: {total_blocked}", flush=True)
    print(f"Total resolution errors: {total_errors}", flush=True)
    if aggregate:
        print(flush=True)
        print(
            "Recommended `overrides` entries to add to each affected package.json:",
            flush=True,
        )
        for pj, ov in aggregate.items():
            print(flush=True)
            print(f"  {pj}", flush=True)
            block = json.dumps(ov, indent=4, sort_keys=True).replace("\n", "\n    ")
            print(f'    "overrides": {block}', flush=True)
    print(flush=True)
    return total_blocked + total_errors


def main() -> int:
    p = argparse.ArgumentParser(
        description="Preflight one or more package.json files against DFU's package-age policy."
    )
    p.add_argument("package_json", nargs="+", type=Path)
    p.add_argument(
        "--min-package-age-days",
        type=int,
        default=3,
        help="Minimum package age in days (default: 3, matches DFU default)",
    )
    p.add_argument("--registry", default="https://registry.npmjs.org/")
    p.add_argument("--workers", type=int, default=16)
    args = p.parse_args()

    reports = []
    for pj in args.package_json:
        print(f"=> Resolving {pj}", file=sys.stderr, flush=True)
        reports.append(
            preflight_one(pj, args.min_package_age_days, args.registry, args.workers)
        )

    issues = print_report(reports, args.min_package_age_days)
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
