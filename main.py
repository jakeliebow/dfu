import argparse
from proxy import run_proxy


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8080, help="Proxy port")
    p.add_argument("--host", default="localhost", help="Proxy host address")
    p.add_argument(
        "--min-package-age-days",
        type=int,
        default=3,
        help="Minimum package age in days (default: 14 days)",
    )
    p.add_argument(
        "--registry",
        default="https://registry.npmjs.org/",
        help="Package registry URL (default: https://registry.npmjs.org/)",
    )
    args = p.parse_args()
    run_proxy(args.host, args.port, args.min_package_age_days, args.registry)



if __name__ == "__main__":
    main()
